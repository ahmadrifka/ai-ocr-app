"""PostgreSQL-polled OCR worker; run separately from the FastAPI process."""

import asyncio
import datetime as dt
import logging
from pathlib import Path
from time import perf_counter
import uuid
from typing import Awaitable, Callable

from sqlalchemy import func, select, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import async_session, engine
from app.models import OcrJob, Transaction
from app.schemas import AnalysisResult
from app.services.accounts import beneficiary_is_account, source_is_account
from app.services.dedupe import image_dedupe_key, transaction_dedupe_key
from app.services.filestore import delete_file, resolve_file
from app.services.llm import analyze_image
from app.services.ocr_guardrails import review_flags


logger = logging.getLogger(__name__)
MAX_OCR_ATTEMPTS = 5
LEGACY_IMAGE_DEDUPE_SCAN_LIMIT = 100
POLL_INTERVAL_SECONDS = 1
JOB_LEASE_SECONDS = 300
OCR_TIMEOUT_SECONDS = 240
RETRY_BASE_SECONDS = 2


async def _claim_next_job(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, str, str] | None:
    now = dt.datetime.now(dt.timezone.utc)
    async with sessions() as session:
        async with session.begin():
            stmt = (
                select(OcrJob)
                .where(
                    or_(
                        and_(OcrJob.status == "PENDING", OcrJob.available_at <= func.now()),
                        and_(
                            OcrJob.status == "PROCESSING",
                            OcrJob.lease_until <= func.now(),
                        ),
                    )
                )
                .order_by(OcrJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            job = await session.scalar(stmt)
            if job is None:
                return None
            if job.attempt_count >= MAX_OCR_ATTEMPTS:
                job.status = "FAILED"
                job.lease_until = None
                job.last_error = "Worker lease expired after maximum attempts"
                return None

            job.status = "PROCESSING"
            job.attempt_count += 1
            job.lease_until = now + dt.timedelta(seconds=JOB_LEASE_SECONDS)
            claimed = (job.upload_id, job.asset_path or "", job.content_type)
        return claimed


async def _save_failure(
    sessions: async_sessionmaker[AsyncSession],
    upload_id,
    error: Exception,
    *,
    ai_analysis_duration_ms: int | None = None,
) -> None:
    async with sessions() as session:
        async with session.begin():
            job = await session.get(OcrJob, upload_id)
            if job is None or job.status != "PROCESSING":
                return
            job.lease_until = None
            job.last_error = type(error).__name__
            if ai_analysis_duration_ms is not None:
                job.ai_analysis_duration_ms = ai_analysis_duration_ms
            if job.attempt_count >= MAX_OCR_ATTEMPTS:
                job.status = "FAILED"
            else:
                job.status = "PENDING"
                delay = RETRY_BASE_SECONDS * (2 ** (job.attempt_count - 1))
                job.available_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                    seconds=delay
                )


async def _mark_duplicate(
    sessions: async_sessionmaker[AsyncSession], upload_id, dedupe_key: str
) -> tuple[str | None, str | None] | None:
    async with sessions() as session:
        async with session.begin():
            existing = await session.scalar(
                select(Transaction).where(Transaction.dedupe_key == dedupe_key)
            )
            job = await session.get(OcrJob, upload_id)
            if existing is None or job is None:
                return None
            uploaded_asset_path = job.asset_path
            matched_asset_path = existing.asset_path
            job.status = "DUPLICATE"
            job.transaction_record_id = existing.id
            job.asset_path = matched_asset_path
            job.lease_until = None
            job.last_error = None
    return uploaded_asset_path, matched_asset_path


async def _delete_duplicate_upload_asset(
    upload_id: uuid.UUID,
    uploaded_asset_path: str | None,
    matched_asset_path: str | None,
) -> None:
    if not uploaded_asset_path or uploaded_asset_path == matched_asset_path:
        return
    try:
        await delete_file(uploaded_asset_path)
    except (OSError, ValueError):
        logger.warning("Could not clean duplicate upload %s", upload_id)


async def _cleanup_duplicate_assets(
    sessions: async_sessionmaker[AsyncSession],
) -> bool:
    async with sessions() as session:
        jobs = list(
            (
                await session.scalars(
                    select(OcrJob)
                    .where(OcrJob.status == "DUPLICATE", OcrJob.asset_path.is_not(None))
                    .order_by(OcrJob.created_at)
                    .limit(20)
                )
            ).all()
        )
        asset_paths = {job.asset_path for job in jobs if job.asset_path}
        referenced_paths = set()
        if asset_paths:
            referenced_paths = set(
                (
                    await session.scalars(
                        select(Transaction.asset_path).where(
                            Transaction.asset_path.in_(asset_paths)
                        )
                    )
                ).all()
            )
    cleaned_any = False
    for job in jobs:
        if not job.asset_path or job.asset_path in referenced_paths:
            continue
        try:
            await delete_file(job.asset_path)
        except (OSError, ValueError):
            logger.warning("Could not clean duplicate upload %s", job.upload_id)
            continue
        async with sessions() as session:
            async with session.begin():
                current = await session.get(OcrJob, job.upload_id)
                if (
                    current is not None
                    and current.status == "DUPLICATE"
                    and current.asset_path == job.asset_path
                ):
                    current.asset_path = None
        cleaned_any = True
    return cleaned_any


def _is_dedupe_conflict(error: IntegrityError) -> bool:
    message = str(error.orig).lower()
    return "transaction_dedupe_key_uq" in message or "transaction.dedupe_key" in message


async def _find_legacy_image_duplicate_id(
    sessions: async_sessionmaker[AsyncSession],
    analysis: AnalysisResult,
    image_key: str,
) -> int | None:
    if analysis.amount is None or analysis.transaction_date is None:
        return None

    stmt = (
        select(Transaction.id, Transaction.asset_path)
        .where(
            Transaction.dedupe_key.is_(None),
            Transaction.amount == analysis.amount,
            Transaction.transaction_date == analysis.transaction_date,
        )
        .order_by(Transaction.id.desc())
        .limit(LEGACY_IMAGE_DEDUPE_SCAN_LIMIT)
    )
    async with sessions() as session:
        candidates = (await session.execute(stmt)).all()

    for transaction_id, asset_path in candidates:
        if not asset_path:
            continue
        try:
            candidate_path = resolve_file(asset_path)
            candidate_bytes = await asyncio.to_thread(candidate_path.read_bytes)
        except (OSError, ValueError):
            continue
        if image_dedupe_key(candidate_bytes) == image_key:
            return transaction_id
    return None


async def process_next_job(
    sessions: async_sessionmaker[AsyncSession],
    *,
    analyzer: Callable[[bytes, str], Awaitable[AnalysisResult]] = analyze_image,
) -> bool:
    """Claim and process one OCR job; return whether work was performed."""
    cleaned_duplicates = await _cleanup_duplicate_assets(sessions)
    claimed = await _claim_next_job(sessions)
    if claimed is None:
        return cleaned_duplicates

    upload_id, asset_path, content_type = claimed
    dedupe_key = None
    legacy_image_duplicate_id = None
    matched_asset_path = None
    ai_analysis_duration_ms = None
    try:
        image_path: Path = resolve_file(asset_path)
        image_bytes = await asyncio.to_thread(image_path.read_bytes)
        analysis_started_at = perf_counter()
        try:
            analysis = await asyncio.wait_for(
                analyzer(image_bytes, content_type), timeout=OCR_TIMEOUT_SECONDS
            )
        finally:
            ai_analysis_duration_ms = round(
                (perf_counter() - analysis_started_at) * 1000
            )
        if not isinstance(analysis, AnalysisResult):
            analysis = AnalysisResult.model_validate(analysis)
        if not analysis.is_receipt:
            async with sessions() as session:
                async with session.begin():
                    job = await session.get(OcrJob, upload_id)
                    if job is None or job.status != "PROCESSING":
                        return True
                    job.status = "FAILED"
                    job.lease_until = None
                    job.last_error = "not_a_receipt"
                    job.ai_analysis_duration_ms = ai_analysis_duration_ms
            return True

        dedupe_key = transaction_dedupe_key(
            analysis.source_bank,
            analysis.transaction_id,
            analysis.amount,
            analysis.transaction_date,
        )
        if dedupe_key is None:
            dedupe_key = image_dedupe_key(image_bytes)
            legacy_image_duplicate_id = await _find_legacy_image_duplicate_id(
                sessions, analysis, dedupe_key
            )

        duplicate = False
        async with sessions() as session:
            async with session.begin():
                current_job = await session.get(OcrJob, upload_id)
                if current_job is None or current_job.status != "PROCESSING":
                    return True
                current_job.ai_analysis_duration_ms = ai_analysis_duration_ms
                if dedupe_key:
                    existing = await session.scalar(
                        select(Transaction).where(Transaction.dedupe_key == dedupe_key)
                    )
                else:
                    existing = None
                if existing is None and legacy_image_duplicate_id is not None:
                    existing = await session.get(Transaction, legacy_image_duplicate_id)
                if existing is not None:
                    if legacy_image_duplicate_id is not None and existing.dedupe_key is None:
                        existing.dedupe_key = dedupe_key
                    matched_asset_path = existing.asset_path
                    current_job.asset_path = matched_asset_path
                    current_job.status = "DUPLICATE"
                    current_job.transaction_record_id = existing.id
                    current_job.lease_until = None
                    current_job.last_error = None
                    duplicate = True
                else:
                    # OCR is constrained to EXPENSES; account matches set direction types.
                    source_account_is_ours = await source_is_account(session, analysis)
                    beneficiary_account_is_ours = await beneficiary_is_account(
                        session, analysis
                    )
                    is_transfer = source_account_is_ours and beneficiary_account_is_ours
                    incoming = beneficiary_account_is_ours and not is_transfer
                    transaction = Transaction(
                        transaction_date=analysis.transaction_date,
                        transaction_id=analysis.transaction_id,
                        dedupe_key=dedupe_key,
                        description=analysis.description,
                        review_flags=review_flags(analysis.description),
                        category="Penjualan" if incoming else analysis.category,
                        sub_category="Penjualan Produk" if incoming else analysis.sub_category,
                        transaction_type=(
                            "TRANSFER"
                            if is_transfer
                            else "INCOMING" if incoming else analysis.transaction_type
                        ),
                        beneficiary_bank=analysis.beneficiary_bank,
                        beneficiary_account_number=analysis.beneficiary_account_number,
                        benecifiacry_account_name=analysis.benecifiacry_account_name,
                        source_bank=analysis.source_bank,
                        source_account_number=analysis.source_account_number,
                        source_account_name=analysis.source_account_name,
                        amount=analysis.amount,
                        asset_path=asset_path,
                    )
                    session.add(transaction)
                    await session.flush()
                    current_job.status = "COMPLETED"
                    current_job.transaction_record_id = transaction.id
                    current_job.lease_until = None
                    current_job.last_error = None

        if duplicate:
            await _delete_duplicate_upload_asset(
                upload_id, asset_path, matched_asset_path
            )
            await _cleanup_duplicate_assets(sessions)
        return True
    except IntegrityError as exc:
        if dedupe_key and _is_dedupe_conflict(exc):
            duplicate_paths = await _mark_duplicate(sessions, upload_id, dedupe_key)
            if duplicate_paths is not None:
                uploaded_asset_path, matched_asset_path = duplicate_paths
                await _delete_duplicate_upload_asset(
                    upload_id, uploaded_asset_path, matched_asset_path
                )
                await _cleanup_duplicate_assets(sessions)
                return True
        await _save_failure(
            sessions, upload_id, exc,
            ai_analysis_duration_ms=ai_analysis_duration_ms,
        )
        return True
    except Exception as exc:
        await _save_failure(
            sessions, upload_id, exc,
            ai_analysis_duration_ms=ai_analysis_duration_ms,
        )
        return True


async def run_worker() -> None:
    logger.info("Starting OCR worker")
    try:
        while True:
            try:
                did_work = await process_next_job(async_session)
            except Exception:
                logger.exception("OCR worker iteration failed")
                did_work = False
            if not did_work:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())

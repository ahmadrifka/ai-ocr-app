"""Create durable OCR upload jobs with request-level idempotency."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OcrJob
from app.services.filestore import delete_file, save_file


async def create_upload_job(
    session: AsyncSession,
    *,
    filename: str,
    content_type: str,
    content: bytes,
    idempotency_key: str,
) -> OcrJob:
    existing = await session.scalar(
        select(OcrJob).where(OcrJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing

    upload_id = uuid.uuid4()
    asset_path = await save_file(
        filename,
        content,
        content_type=content_type,
        upload_id=upload_id,
    )
    job = OcrJob(
        upload_id=upload_id,
        idempotency_key=idempotency_key,
        asset_path=asset_path,
        content_type=content_type,
        status="PENDING",
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        await delete_file(asset_path)
        existing = await session.scalar(
            select(OcrJob).where(OcrJob.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return existing
    except Exception:
        await session.rollback()
        existing = await session.scalar(
            select(OcrJob).where(OcrJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.asset_path != asset_path:
                await delete_file(asset_path)
            return existing
        try:
            await delete_file(asset_path)
        except (OSError, ValueError):
            pass
        raise

    await session.refresh(job)
    return job

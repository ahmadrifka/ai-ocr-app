import asyncio
import datetime as dt
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import OcrJob, Transaction
from app.schemas import AnalysisResult
from app.services.dedupe import transaction_dedupe_key
from app.services.filestore import resolve_file
from app.services.uploads import create_upload_job
from app.services.worker import MAX_OCR_ATTEMPTS, process_next_job, run_worker


class OcrPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.filestore_patch = patch(
            "app.services.filestore.FILESTORE_PATH", self.temp_dir.name
        )
        self.filestore_patch.start()
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.filestore_patch.stop()
        self.temp_dir.cleanup()

    async def create_upload(self, key: str, image: bytes = b"image") -> OcrJob:
        async with self.sessions() as session:
            return await create_upload_job(
                session,
                filename="receipt.png",
                content_type="image/png",
                content=image,
                idempotency_key=key,
            )

    def result(self, **overrides) -> AnalysisResult:
        values = {
            "transaction_id": "TRX-123",
            "transaction_date": dt.datetime(2026, 11, 17, 9, 30, tzinfo=dt.timezone.utc),
            "description": "Office supplies",
            "category": "Biaya-Perlengkapan Kantor dan Administrasi",
            "transaction_type": "EXPENSES",
            "source_bank": "Bank Central Asia",
            "amount": Decimal("125000.00"),
        }
        values.update(overrides)
        return AnalysisResult(**values)

    async def test_same_idempotency_key_reuses_upload_and_file(self):
        first = await self.create_upload("request-1", b"first")
        second = await self.create_upload("request-1", b"different retry body")

        self.assertEqual(first.upload_id, second.upload_id)
        self.assertEqual(first.asset_path, second.asset_path)
        self.assertEqual(len(list(Path(self.temp_dir.name).rglob("*.png"))), 1)
        self.assertRegex(first.asset_path, r"^\d{4}/\d{2}/\d{2}/[0-9a-f-]+\.png$")

    async def test_upload_cleans_file_when_database_insert_fails(self):
        with patch.object(
            AsyncSession,
            "commit",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ):
            async with self.sessions() as session:
                with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                    await create_upload_job(
                        session,
                        filename="receipt.png",
                        content_type="image/png",
                        content=b"image",
                        idempotency_key="request-db-error",
                    )

        self.assertEqual(len(list(Path(self.temp_dir.name).rglob("*.png"))), 0)

    async def test_successful_worker_persists_transaction_and_completes_job(self):
        job = await self.create_upload("request-success")
        image_path = resolve_file(job.asset_path)

        async def analyzer(_image, _mime):
            return self.result()

        processed = await process_next_job(self.sessions, analyzer=analyzer)

        self.assertTrue(processed)
        async with self.sessions() as session:
            saved_job = await session.get(OcrJob, job.upload_id)
            transactions = list((await session.scalars(select(Transaction))).all())
        self.assertEqual(saved_job.status, "COMPLETED")
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].transaction_id, "TRX-123")
        self.assertEqual(saved_job.transaction_record_id, transactions[0].id)
        self.assertTrue(image_path.is_file())

    async def test_sqlite_worker_matches_beneficiary_against_local_accounts(self):
        job = await self.create_upload("request-incoming")
        async with self.engine.begin() as connection:
            await connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS accounts "
                "(account_number TEXT, account_name TEXT, bank_name TEXT)"
            )
            await connection.exec_driver_sql(
                "INSERT INTO accounts VALUES ('1234', 'Our account', 'Bank Central Asia')"
            )

        async def analyzer(_image, _mime):
            return self.result(
                beneficiary_account_number="12-34",
                beneficiary_bank="Bank Central Asia",
                benecifiacry_account_name="Our account",
            )

        await process_next_job(self.sessions, analyzer=analyzer)

        async with self.sessions() as session:
            saved_job = await session.get(OcrJob, job.upload_id)
            transaction = await session.scalar(select(Transaction))
        self.assertEqual(saved_job.status, "COMPLETED")
        self.assertEqual(transaction.transaction_type, "INCOMING")
        self.assertEqual(transaction.category, "sale")

    async def test_duplicate_transaction_deletes_new_image_and_keeps_original(self):
        first = await self.create_upload("request-first")
        second = await self.create_upload("request-second")
        first_path = resolve_file(first.asset_path)
        second_path = resolve_file(second.asset_path)

        async def analyzer(_image, _mime):
            return self.result()

        await process_next_job(self.sessions, analyzer=analyzer)
        await process_next_job(self.sessions, analyzer=analyzer)

        async with self.sessions() as session:
            saved_first = await session.get(OcrJob, first.upload_id)
            saved_second = await session.get(OcrJob, second.upload_id)
            transactions = list((await session.scalars(select(Transaction))).all())
        self.assertEqual(saved_first.status, "COMPLETED")
        self.assertEqual(saved_second.status, "DUPLICATE")
        self.assertEqual(len(transactions), 1)
        self.assertTrue(first_path.is_file())
        self.assertFalse(second_path.exists())

    async def test_missing_transaction_id_skips_dedupe_and_keeps_both_images(self):
        first = await self.create_upload("request-no-reference-1")
        second = await self.create_upload("request-no-reference-2")
        image_paths = [resolve_file(first.asset_path), resolve_file(second.asset_path)]

        async def analyzer(_image, _mime):
            return self.result(transaction_id=None)

        await process_next_job(self.sessions, analyzer=analyzer)
        await process_next_job(self.sessions, analyzer=analyzer)

        async with self.sessions() as session:
            jobs = [
                await session.get(OcrJob, first.upload_id),
                await session.get(OcrJob, second.upload_id),
            ]
            transactions = list((await session.scalars(select(Transaction))).all())
        self.assertEqual([job.status for job in jobs], ["COMPLETED", "COMPLETED"])
        self.assertEqual(len(transactions), 2)
        self.assertTrue(all(path.is_file() for path in image_paths))

    async def test_failed_ocr_retries_then_keeps_image_for_review(self):
        job = await self.create_upload("request-failure")
        image_path = resolve_file(job.asset_path)

        async def analyzer(_image, _mime):
            raise RuntimeError("temporary provider failure")

        for _ in range(MAX_OCR_ATTEMPTS):
            async with self.sessions() as session:
                pending = await session.get(OcrJob, job.upload_id)
                pending.available_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
                await session.commit()
            await process_next_job(self.sessions, analyzer=analyzer)

        async with self.sessions() as session:
            saved_job = await session.get(OcrJob, job.upload_id)
        self.assertEqual(saved_job.status, "FAILED")
        self.assertEqual(saved_job.attempt_count, MAX_OCR_ATTEMPTS)
        self.assertTrue(image_path.is_file())

    async def test_worker_survives_transient_iteration_errors(self):
        calls = 0

        async def process(_sessions):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary database outage")
            raise asyncio.CancelledError

        with (
            patch("app.services.worker.process_next_job", new=process),
            patch("app.services.worker.asyncio.sleep", new_callable=AsyncMock) as sleep,
            patch(
                "app.services.worker.engine",
                new=SimpleNamespace(dispose=AsyncMock()),
            ),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await run_worker()

        self.assertEqual(calls, 2)
        sleep.assert_awaited_once()

    def test_dedupe_key_requires_all_fields_and_normalizes_reference_and_bank(self):
        event_date = dt.datetime(2026, 11, 17, 9, 30, tzinfo=dt.timezone.utc)
        first = transaction_dedupe_key(
            "Bank Central Asia", "TRX-123", Decimal("125000.00"), event_date
        )
        equivalent = transaction_dedupe_key(
            "bank-central asia", "trx 123", Decimal("125000"), event_date
        )
        self.assertIsNotNone(first)
        self.assertEqual(first, equivalent)
        self.assertIsNone(
            transaction_dedupe_key("BCA", None, Decimal("1"), event_date)
        )


if __name__ == "__main__":
    unittest.main()

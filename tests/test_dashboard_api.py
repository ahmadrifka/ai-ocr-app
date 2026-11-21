import datetime as dt
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models import OcrJob, Transaction, accounts_table
from app.routers.documents import list_uploads
from app.services.dedupe import image_dedupe_key, transaction_dedupe_key


class UploadListingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_lists_newest_uploads_first_and_respects_page_limit(self):
        older_id = uuid.uuid4()
        newer_id = uuid.uuid4()
        older_time = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        newer_time = dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc)

        async with self.sessions() as session:
            session.add_all(
                [
                    OcrJob(
                        upload_id=older_id,
                        idempotency_key="older-request",
                        content_type="image/jpeg",
                        status="COMPLETED",
                        attempt_count=1,
                        available_at=older_time,
                        created_at=older_time,
                    ),
                    OcrJob(
                        upload_id=newer_id,
                        idempotency_key="newer-request",
                        content_type="image/jpeg",
                        status="PROCESSING",
                        attempt_count=2,
                        available_at=newer_time,
                        created_at=newer_time,
                    ),
                ]
            )
            await session.commit()

        async with self.sessions() as session:
            first_page = await list_uploads(skip=0, limit=1, db=session)
            second_page = await list_uploads(skip=1, limit=1, db=session)

        self.assertEqual([job.upload_id for job in first_page], [newer_id])
        self.assertEqual([job.upload_id for job in second_page], [older_id])
        self.assertEqual(first_page[0].status, "PROCESSING")
        self.assertEqual(first_page[0].attempt_count, 2)

    async def test_http_routes_serialize_jobs_and_bound_page_parameters(self):
        upload_id = uuid.uuid4()
        async with self.sessions() as session:
            session.add(
                OcrJob(
                    upload_id=upload_id,
                    idempotency_key="http-request",
                    content_type="image/jpeg",
                    status="PENDING",
                    attempt_count=0,
                    available_at=dt.datetime.now(dt.timezone.utc),
                )
            )
            await session.commit()

        previous_overrides = app.dependency_overrides.copy()

        async def override_db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/documents/uploads?limit=20")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload[0]["upload_id"], str(upload_id))
                self.assertEqual(payload[0]["status"], "PENDING")
                self.assertEqual(payload[0]["content_type"], "image/jpeg")
                self.assertIsNone(payload[0]["last_error"])
                self.assertIn("created_at", payload[0])

                oversized_jobs = await client.get("/api/documents/uploads?limit=51")
                oversized_transactions = await client.get("/api/documents/?limit=51")
                negative_offset = await client.get("/api/documents/?skip=-1")

                self.assertEqual(oversized_jobs.status_code, 422)
                self.assertEqual(oversized_transactions.status_code, 422)
                self.assertEqual(negative_offset.status_code, 422)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)

    async def test_failed_upload_responses_include_error_and_processing_details(self):
        upload_id = uuid.uuid4()
        created_at = dt.datetime.now(dt.timezone.utc)
        async with self.sessions() as session:
            session.add(
                OcrJob(
                    upload_id=upload_id,
                    idempotency_key="failed-request",
                    content_type="image/jpeg",
                    status="FAILED",
                    attempt_count=1,
                    ai_analysis_duration_ms=875,
                    last_error="not_a_receipt",
                    created_at=created_at,
                    available_at=created_at,
                )
            )
            await session.commit()

        previous_overrides = app.dependency_overrides.copy()

        async def override_db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                listed = await client.get("/api/documents/uploads")
                status = await client.get(f"/api/documents/uploads/{upload_id}")

            self.assertEqual(listed.status_code, 200)
            job = listed.json()[0]
            self.assertEqual(job["upload_id"], str(upload_id))
            self.assertEqual(job["status"], "FAILED")
            self.assertEqual(job["attempt_count"], 1)
            self.assertEqual(job["ai_analysis_duration_ms"], 875)
            self.assertEqual(job["content_type"], "image/jpeg")
            self.assertEqual(job["last_error"], "not_a_receipt")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["last_error"], "not_a_receipt")
            self.assertEqual(status.json()["ai_analysis_duration_ms"], 875)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)

    async def test_upload_image_route_serves_image_and_rejects_missing_or_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as file_root:
            stored_path = "2026/11/21/upload.jpg"
            image_path = Path(file_root) / stored_path
            image_path.parent.mkdir(parents=True)
            image_bytes = b"upload-image-test"
            image_path.write_bytes(image_bytes)
            upload_ids = [uuid.uuid4() for _ in range(3)]

            async with self.sessions() as session:
                session.add_all(
                    [
                        OcrJob(
                            upload_id=upload_ids[0],
                            idempotency_key="stored-upload-image",
                            content_type="image/jpeg",
                            status="FAILED",
                            attempt_count=1,
                            asset_path=stored_path,
                        ),
                        OcrJob(
                            upload_id=upload_ids[1],
                            idempotency_key="missing-upload-image",
                            content_type="image/jpeg",
                            status="FAILED",
                            attempt_count=1,
                            asset_path="2026/11/21/missing.jpg",
                        ),
                        OcrJob(
                            upload_id=upload_ids[2],
                            idempotency_key="unsafe-upload-image",
                            content_type="image/jpeg",
                            status="FAILED",
                            attempt_count=1,
                            asset_path="../outside.jpg",
                        ),
                    ]
                )
                await session.commit()

            previous_overrides = app.dependency_overrides.copy()

            async def override_db():
                async with self.sessions() as session:
                    yield session

            app.dependency_overrides[get_db] = override_db
            try:
                with patch("app.services.filestore.FILESTORE_PATH", file_root):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get(
                            f"/api/documents/uploads/{upload_ids[0]}/image"
                        )
                        missing = await client.get(
                            f"/api/documents/uploads/{upload_ids[1]}/image"
                        )
                        unsafe = await client.get(
                            f"/api/documents/uploads/{upload_ids[2]}/image"
                        )
                        unknown = await client.get(
                            f"/api/documents/uploads/{uuid.uuid4()}/image"
                        )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, image_bytes)
                self.assertEqual(response.headers["content-type"], "image/jpeg")
                self.assertTrue(response.headers["content-disposition"].startswith("inline;"))
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                self.assertEqual(missing.status_code, 404)
                self.assertEqual(unsafe.status_code, 404)
                self.assertEqual(unknown.status_code, 404)
            finally:
                app.dependency_overrides.clear()
                app.dependency_overrides.update(previous_overrides)

    async def test_dashboard_can_update_transaction_and_reject_invalid_amount(self):
        async with self.sessions() as session:
            transaction = Transaction(
                description="share OTP",
                category="Uncategorized",
                transaction_type="EXPENSES",
                transaction_id="REF-1",
                transaction_date=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                source_bank="Bank A",
                amount=100,
                review_flags=["sensitive_credentials_request"],
                asset_path="receipt.jpg",
            )
            transaction.dedupe_key = transaction_dedupe_key(
                transaction.source_bank,
                transaction.transaction_id,
                transaction.amount,
                transaction.transaction_date,
            )
            session.add(transaction)
            await session.commit()
            transaction_id = transaction.id

        previous_overrides = app.dependency_overrides.copy()

        async def override_db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                updated = await client.patch(
                    f"/api/documents/{transaction_id}",
                    json={
                        "description": "corrected description",
                        "amount": 250,
                        "transaction_type": "TRANSFER",
                    },
                )
                invalid = await client.patch(
                    f"/api/documents/{transaction_id}", json={"amount": -1}
                )
                empty = await client.patch(f"/api/documents/{transaction_id}", json={})
                null_description = await client.patch(
                    f"/api/documents/{transaction_id}", json={"description": None}
                )
                invalid_category = await client.patch(
                    f"/api/documents/{transaction_id}", json={"category": "not-a-category"}
                )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["description"], "corrected description")
            self.assertEqual(updated.json()["amount"], "250.00")
            self.assertEqual(updated.json()["transaction_type"], "TRANSFER")
            self.assertEqual(updated.json()["category"], "Uncategorized")
            self.assertEqual(updated.json()["review_flags"], [])
            async with self.sessions() as session:
                saved = await session.get(Transaction, transaction_id)
            self.assertIsNotNone(saved)
            self.assertEqual(
                saved.dedupe_key,
                transaction_dedupe_key(
                    saved.source_bank,
                    saved.transaction_id,
                    saved.amount,
                    saved.transaction_date,
                ),
            )
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(empty.status_code, 422)
            self.assertEqual(null_description.status_code, 422)
            self.assertEqual(invalid_category.status_code, 422)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)

    async def test_patch_preserves_image_fingerprint_when_bank_key_is_unavailable(self):
        image_key = image_dedupe_key(b"payroll-slip-image")
        async with self.sessions() as session:
            transaction = Transaction(
                description="Monthly payroll",
                category="Uncategorized",
                transaction_type="EXPENSES",
                transaction_id=None,
                transaction_date=dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
                source_bank=None,
                amount=100,
                review_flags=[],
                asset_path="payroll.jpg",
                dedupe_key=image_key,
            )
            session.add(transaction)
            await session.commit()
            transaction_record_id = transaction.id

        previous_overrides = app.dependency_overrides.copy()

        async def override_db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.patch(
                    f"/api/documents/{transaction_record_id}", json={"amount": 125}
                )
            self.assertEqual(response.status_code, 200)
            async with self.sessions() as session:
                saved = await session.get(Transaction, transaction_record_id)
            if saved is None:
                self.fail("updated transaction was not found")
            self.assertEqual(saved.dedupe_key, image_key)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)

    async def test_dashboard_can_list_and_update_a_bank_account(self):
        async with self.sessions() as session:
            await session.execute(
                accounts_table.insert().values(
                    account_number="12345", account_name="Old Name", bank_name="Bank A"
                )
            )
            await session.commit()

        previous_overrides = app.dependency_overrides.copy()

        async def override_db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                listed = await client.get("/api/accounts")
                updated = await client.patch(
                    "/api/accounts",
                    json={
                        "current_account_number": "12345",
                        "current_account_name": "Old Name",
                        "current_bank_name": "Bank A",
                        "account_number": "67890",
                        "account_name": "New Name",
                        "bank_name": "Bank B",
                    },
                )
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()[0]["account_name"], "Old Name")
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["account_name"], "New Name")
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)

    async def test_account_update_rejects_ambiguous_duplicate_rows(self):
        async with self.sessions() as session:
            await session.execute(
                accounts_table.insert().values(
                    account_number="12345", account_name="Duplicate", bank_name="Bank A"
                )
            )
            await session.execute(
                accounts_table.insert().values(
                    account_number="12345", account_name="Duplicate", bank_name="Bank A"
                )
            )
            await session.commit()

        previous_overrides = app.dependency_overrides.copy()

        async def override_db():
            async with self.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.patch(
                    "/api/accounts",
                    json={
                        "current_account_number": "12345",
                        "current_account_name": "Duplicate",
                        "current_bank_name": "Bank A",
                        "account_number": "67890",
                        "account_name": "Changed",
                        "bank_name": "Bank B",
                    },
                )
            self.assertEqual(response.status_code, 409)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)

    async def test_receipt_route_serves_image_and_rejects_missing_or_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as file_root:
            stored_path = "2026/11/19/receipt.jpg"
            image_path = Path(file_root) / stored_path
            image_path.parent.mkdir(parents=True)
            image_bytes = b"receipt-image-test"
            image_path.write_bytes(image_bytes)

            async with self.sessions() as session:
                records = [
                    Transaction(
                        description="stored image",
                        category="Uncategorized",
                        transaction_type="EXPENSES",
                        asset_path=stored_path,
                    ),
                    Transaction(
                        description="missing image",
                        category="Uncategorized",
                        transaction_type="EXPENSES",
                        asset_path="2026/11/19/missing.jpg",
                    ),
                    Transaction(
                        description="unsafe path",
                        category="Uncategorized",
                        transaction_type="EXPENSES",
                        asset_path="../outside.jpg",
                    ),
                ]
                session.add_all(records)
                await session.commit()
                stored_id, missing_id, unsafe_id = [record.id for record in records]

            previous_overrides = app.dependency_overrides.copy()

            async def override_db():
                async with self.sessions() as session:
                    yield session

            app.dependency_overrides[get_db] = override_db
            try:
                with patch("app.services.filestore.FILESTORE_PATH", file_root):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        response = await client.get(
                            f"/api/documents/{stored_id}/receipt"
                        )
                        missing = await client.get(
                            f"/api/documents/{missing_id}/receipt"
                        )
                        unsafe = await client.get(
                            f"/api/documents/{unsafe_id}/receipt"
                        )
                        unknown = await client.get("/api/documents/999999/receipt")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, image_bytes)
                self.assertEqual(response.headers["content-type"], "image/jpeg")
                self.assertTrue(
                    response.headers["content-disposition"].startswith("inline;")
                )
                self.assertEqual(missing.status_code, 404)
                self.assertEqual(unsafe.status_code, 404)
                self.assertEqual(unknown.status_code, 404)
            finally:
                app.dependency_overrides.clear()
                app.dependency_overrides.update(previous_overrides)


if __name__ == "__main__":
    unittest.main()

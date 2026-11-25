import json
import unittest
import uuid
from unittest.mock import patch

import httpx

from app.services import filestore
from app.services.supabase_storage import SupabaseStorage, SupabaseStorageError


BASE_URL = "https://project.supabase.co"
BUCKET = "receipts"


class RecordingTransport:
    """Capture requests and answer with a configurable response."""

    def __init__(self, status_code: int = 200, content: bytes = b"{}") -> None:
        self.requests: list[httpx.Request] = []
        self.status_code = status_code
        self.content = content

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status_code, content=self.content)

    def storage(self, secret_key: str = "sb_secret_test") -> SupabaseStorage:
        return SupabaseStorage(
            BASE_URL, secret_key, BUCKET, transport=httpx.MockTransport(self)
        )


class SupabaseStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_posts_object_with_content_type_and_secret_key(self):
        transport = RecordingTransport()

        await transport.storage().upload("2026/11/24/a.jpg", b"image", "image/jpeg")

        request = transport.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            str(request.url), f"{BASE_URL}/storage/v1/object/{BUCKET}/2026/11/24/a.jpg"
        )
        self.assertEqual(request.content, b"image")
        self.assertEqual(request.headers["content-type"], "image/jpeg")
        self.assertEqual(request.headers["apikey"], "sb_secret_test")
        self.assertNotIn("authorization", request.headers)

    async def test_legacy_jwt_key_is_also_sent_as_bearer_token(self):
        transport = RecordingTransport()

        await transport.storage("eyJlegacy").upload("a.jpg", b"image", "image/jpeg")

        self.assertEqual(transport.requests[0].headers["authorization"], "Bearer eyJlegacy")

    async def test_download_returns_object_bytes(self):
        transport = RecordingTransport(content=b"stored-image")

        content = await transport.storage().download("2026/11/24/a.jpg")

        self.assertEqual(content, b"stored-image")
        self.assertEqual(transport.requests[0].method, "GET")

    async def test_download_of_missing_object_raises_file_not_found(self):
        for status_code in (400, 404):
            with self.subTest(status_code=status_code):
                transport = RecordingTransport(status_code=status_code)
                with self.assertRaises(FileNotFoundError):
                    await transport.storage().download("missing.jpg")

    async def test_delete_sends_prefix_list_to_bucket(self):
        transport = RecordingTransport(content=b"[]")

        await transport.storage().delete("2026/11/24/a.jpg")

        request = transport.requests[0]
        self.assertEqual(request.method, "DELETE")
        self.assertEqual(str(request.url), f"{BASE_URL}/storage/v1/object/{BUCKET}")
        self.assertEqual(json.loads(request.content), {"prefixes": ["2026/11/24/a.jpg"]})

    async def test_server_errors_raise_storage_error_as_os_error(self):
        transport = RecordingTransport(status_code=500)

        with self.assertRaises(SupabaseStorageError) as raised:
            await transport.storage().upload("a.jpg", b"image", "image/jpeg")
        self.assertIsInstance(raised.exception, OSError)

    def test_missing_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            SupabaseStorage("", "key", BUCKET)


class SupabaseFilestoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = RecordingTransport(content=b"stored-image")
        patches = [
            patch.object(filestore, "STORAGE_BACKEND", filestore.SUPABASE_BACKEND),
            patch.object(filestore, "_supabase", return_value=self.transport.storage()),
        ]
        for active in patches:
            active.start()
            self.addCleanup(active.stop)

    async def test_save_read_and_delete_go_through_supabase(self):
        upload_id = uuid.uuid4()

        relative_path = await filestore.save_file(
            "receipt.jpg", b"image", content_type="image/jpeg", upload_id=upload_id
        )
        content = await filestore.read_file(relative_path)
        await filestore.delete_file(relative_path)

        self.assertTrue(relative_path.endswith(f"/{upload_id}.jpg"))
        self.assertEqual(content, b"stored-image")
        self.assertEqual(
            [request.method for request in self.transport.requests], ["POST", "GET", "DELETE"]
        )

    async def test_path_traversal_is_rejected_before_any_request(self):
        for bad_path in ("../secret.jpg", "/etc/passwd", ""):
            with self.subTest(path=bad_path), self.assertRaises(ValueError):
                await filestore.read_file(bad_path)
        self.assertEqual(self.transport.requests, [])


class StorageBackendValidationTests(unittest.TestCase):
    def test_unknown_backend_is_rejected(self):
        with patch.object(filestore, "STORAGE_BACKEND", "s3"):
            with self.assertRaises(ValueError):
                filestore.validate_storage_backend()

    def test_local_backend_needs_no_remote_configuration(self):
        with patch.object(filestore, "STORAGE_BACKEND", filestore.LOCAL_BACKEND):
            filestore.validate_storage_backend()


if __name__ == "__main__":
    unittest.main()

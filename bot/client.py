"""HTTP client for AI OCR FastAPI service."""

import asyncio
import time
from typing import Any
import httpx


API_KEY_HEADER = "X-API-Key"


class OcrApiClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self._auth_headers = {API_KEY_HEADER: api_key} if api_key else {}

    def _client(self, timeout: float) -> httpx.AsyncClient:
        # The API requires authentication in production, so every call carries the key.
        return httpx.AsyncClient(timeout=timeout, headers=self._auth_headers)

    async def check_health(self) -> bool:
        """Check if the FastAPI service is healthy."""
        async with self._client(timeout=10.0) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
            except httpx.RequestError:
                return False

    async def upload_document(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Upload receipt image to OCR API."""
        headers = {"Idempotency-Key": idempotency_key}
        files = {"file": (filename, file_bytes, content_type)}
        async with self._client(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/documents/upload",
                headers=headers,
                files=files,
            )
            response.raise_for_status()
            return response.json()

    async def get_upload_status(self, upload_id: str) -> dict[str, Any]:
        """Fetch OCR upload job status."""
        async with self._client(timeout=15.0) as client:
            response = await client.get(
                f"{self.base_url}/api/documents/uploads/{upload_id}"
            )
            response.raise_for_status()
            return response.json()

    async def get_document(self, document_id: int) -> dict[str, Any]:
        """Fetch saved transaction document by ID."""
        async with self._client(timeout=15.0) as client:
            response = await client.get(
                f"{self.base_url}/api/documents/{document_id}"
            )
            response.raise_for_status()
            return response.json()

    async def update_document(
        self, document_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Update transaction document by ID."""
        async with self._client(timeout=15.0) as client:
            response = await client.patch(
                f"{self.base_url}/api/documents/{document_id}",
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def poll_until_complete(
        self,
        upload_id: str,
        poll_interval: float = 1.5,
        timeout: float = 60.0,
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        """Poll upload job until COMPLETED, DUPLICATE, FAILED or timeout."""
        deadline = time.monotonic() + timeout
        last_status = "PENDING"
        last_error = None

        while time.monotonic() < deadline:
            try:
                job = await self.get_upload_status(upload_id)
            except httpx.RequestError as exc:
                last_error = str(exc)
                await asyncio.sleep(poll_interval)
                continue

            status = job.get("status", "PENDING")
            last_status = status
            last_error = job.get("last_error")

            if status in ("COMPLETED", "DUPLICATE"):
                tx_id = job.get("transaction_record_id")
                if tx_id is not None:
                    try:
                        doc = await self.get_document(int(tx_id))
                        return status, doc, None
                    except httpx.HTTPError:
                        return status, {"id": tx_id}, None
                return status, None, None

            if status == "FAILED":
                return "FAILED", None, last_error

            await asyncio.sleep(poll_interval)

        return last_status, None, "Processing timeout exceeded"

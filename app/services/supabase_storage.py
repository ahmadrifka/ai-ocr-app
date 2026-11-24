"""Minimal async client for a private Supabase Storage bucket."""

from urllib.parse import quote

import httpx


REQUEST_TIMEOUT_SECONDS = 30.0


class SupabaseStorageError(OSError):
    """Raised when Supabase Storage rejects a request.

    Subclasses OSError so callers handle remote storage failures exactly like local
    filesystem failures.
    """


class SupabaseStorage:
    def __init__(
        self,
        base_url: str,
        secret_key: str,
        bucket: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url or not secret_key or not bucket:
            raise ValueError(
                "SUPABASE_URL, SUPABASE_SECRET_KEY and SUPABASE_STORAGE_BUCKET are required"
            )
        self._object_url = f"{base_url.rstrip('/')}/storage/v1/object"
        self._bucket = bucket
        self._headers = _auth_headers(secret_key)
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            transport=self._transport,
        )

    def _url(self, object_path: str) -> str:
        return f"{self._object_url}/{quote(self._bucket)}/{quote(object_path)}"

    async def upload(self, object_path: str, content: bytes, content_type: str) -> None:
        async with self._client() as client:
            response = await client.post(
                self._url(object_path),
                content=content,
                headers={"Content-Type": content_type, "x-upsert": "true"},
            )
        _raise_for_status(response, f"upload {object_path}")

    async def download(self, object_path: str) -> bytes:
        async with self._client() as client:
            response = await client.get(self._url(object_path))
        # Storage reports a missing object as 400 or 404 depending on version.
        if response.status_code in {400, 404}:
            raise FileNotFoundError(object_path)
        _raise_for_status(response, f"download {object_path}")
        return response.content

    async def delete(self, object_path: str) -> None:
        async with self._client() as client:
            response = await client.request(
                "DELETE",
                f"{self._object_url}/{quote(self._bucket)}",
                json={"prefixes": [object_path]},
            )
        _raise_for_status(response, f"delete {object_path}")


def _auth_headers(secret_key: str) -> dict[str, str]:
    headers = {"apikey": secret_key}
    # Legacy service_role keys are JWTs and must also be sent as a bearer token;
    # newer sb_secret_ keys are resolved by the gateway from the apikey header alone.
    if secret_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {secret_key}"
    return headers


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.is_success:
        return
    raise SupabaseStorageError(
        f"Supabase Storage could not {action}: HTTP {response.status_code}"
    )

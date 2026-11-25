"""Store uploaded images under dated paths, on local disk or in Supabase Storage."""

import asyncio
import datetime as dt
from functools import lru_cache
import os
from pathlib import Path, PurePosixPath
import uuid

import aiofiles

from app.config import (
    FILESTORE_PATH,
    STORAGE_BACKEND,
    SUPABASE_SECRET_KEY,
    SUPABASE_STORAGE_BUCKET,
    SUPABASE_URL,
)
from app.services.supabase_storage import SupabaseStorage


LOCAL_BACKEND = "local"
SUPABASE_BACKEND = "supabase"
SUPPORTED_BACKENDS = {LOCAL_BACKEND, SUPABASE_BACKEND}

MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/tiff": ".tiff",
}


async def save_file(
    filename: str,
    content: bytes,
    *,
    content_type: str,
    upload_id: uuid.UUID,
    uploaded_at: dt.datetime | None = None,
) -> str:
    """Save an image under YYYY/MM/DD/<upload_id>.<ext>; return a relative path."""
    uploaded_at = uploaded_at or dt.datetime.now(dt.timezone.utc)
    extension = MIME_EXTENSIONS.get(content_type, Path(filename).suffix.lower() or ".bin")
    relative_path = f"{uploaded_at:%Y/%m/%d}/{upload_id}{extension}"

    if STORAGE_BACKEND == SUPABASE_BACKEND:
        await _supabase().upload(relative_path, content, content_type)
    else:
        await _save_local(relative_path, content)
    return relative_path


async def read_file(relative_path: str) -> bytes:
    """Return stored image bytes; raise FileNotFoundError when the image is gone."""
    if STORAGE_BACKEND == SUPABASE_BACKEND:
        return await _supabase().download(_validated_object_path(relative_path))
    path = resolve_file(relative_path)
    return await asyncio.to_thread(path.read_bytes)


async def delete_file(relative_path: str) -> None:
    """Delete a stored image; a missing image counts as already cleaned up."""
    if STORAGE_BACKEND == SUPABASE_BACKEND:
        await _supabase().delete(_validated_object_path(relative_path))
        return
    path = resolve_file(relative_path)
    await asyncio.to_thread(path.unlink, missing_ok=True)


def resolve_file(relative_path: str) -> Path:
    """Resolve a stored relative path and reject paths outside the local filestore."""
    root = Path(FILESTORE_PATH).resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Stored asset path is outside the filestore")
    return path


def validate_storage_backend() -> None:
    """Fail fast at startup when the storage configuration is unusable."""
    backend = STORAGE_BACKEND
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(
            f"Unsupported STORAGE_BACKEND {backend!r}; use one of {sorted(SUPPORTED_BACKENDS)}"
        )
    if backend == SUPABASE_BACKEND:
        _supabase()


async def _save_local(relative_path: str, content: bytes) -> None:
    absolute_path = resolve_file(relative_path)
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = absolute_path.with_suffix(absolute_path.suffix + ".tmp")
    async with aiofiles.open(temporary_path, "wb") as image_file:
        await image_file.write(content)
    os.replace(temporary_path, absolute_path)


def _validated_object_path(relative_path: str) -> str:
    path = PurePosixPath(relative_path)
    if not relative_path or path.is_absolute() or ".." in path.parts:
        raise ValueError("Stored asset path is outside the filestore")
    return path.as_posix()


@lru_cache(maxsize=1)
def _supabase() -> SupabaseStorage:
    return SupabaseStorage(SUPABASE_URL, SUPABASE_SECRET_KEY, SUPABASE_STORAGE_BUCKET)

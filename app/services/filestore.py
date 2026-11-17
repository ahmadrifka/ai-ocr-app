"""Save uploaded images to a dated local filestore."""

import asyncio
import datetime as dt
import os
from pathlib import Path
import uuid

import aiofiles

from app.config import FILESTORE_PATH


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
    date_path = Path(f"{uploaded_at:%Y/%m/%d}")
    extension = MIME_EXTENSIONS.get(content_type, Path(filename).suffix.lower() or ".bin")
    relative_path = date_path / f"{upload_id}{extension}"
    absolute_path = Path(FILESTORE_PATH) / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = absolute_path.with_suffix(absolute_path.suffix + ".tmp")
    async with aiofiles.open(temporary_path, "wb") as image_file:
        await image_file.write(content)
    os.replace(temporary_path, absolute_path)
    return relative_path.as_posix()


def resolve_file(relative_path: str) -> Path:
    """Resolve a stored relative path and reject paths outside the filestore."""
    root = Path(FILESTORE_PATH).resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Stored asset path is outside the filestore")
    return path


async def delete_file(relative_path: str) -> None:
    """Delete a file if it still exists; missing files are already cleaned up."""
    path = resolve_file(relative_path)
    await asyncio.to_thread(path.unlink, missing_ok=True)

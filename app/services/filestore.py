"""Save uploaded images to local filestore."""

import os
import uuid
import aiofiles

from app.config import FILESTORE_PATH


async def save_file(filename: str, content: bytes) -> str:
    """Save file bytes to filestore. Returns the stored filepath."""
    os.makedirs(FILESTORE_PATH, exist_ok=True)

    ext = os.path.splitext(filename)[1] or ".bin"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(FILESTORE_PATH, stored_name)

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    return filepath

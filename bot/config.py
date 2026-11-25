"""Configuration module for Telegram bot."""

import hashlib
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OCR_API_BASE_URL: str = os.getenv("OCR_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
# Sent as X-API-Key; defaults to the API's own key when the bot runs in the API process.
OCR_API_KEY: str = (os.getenv("OCR_API_KEY") or os.getenv("API_KEY") or "").strip()
BOT_POLL_INTERVAL_SECONDS: float = float(os.getenv("BOT_POLL_INTERVAL_SECONDS", "1.5"))
BOT_POLL_TIMEOUT_SECONDS: float = float(os.getenv("BOT_POLL_TIMEOUT_SECONDS", "60.0"))
ALLOWED_TELEGRAM_USER_IDS: set[int] = {
    int(uid.strip())
    for uid in os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").split(",")
    if uid.strip().isdigit()
}


def _default_webhook_secret(bot_token: str) -> str:
    # Telegram only accepts [A-Za-z0-9_-] here, so derive a stable hex secret from the token.
    if not bot_token:
        return ""
    return hashlib.sha256(f"telegram-webhook:{bot_token}".encode()).hexdigest()


TELEGRAM_WEBHOOK_SECRET: str = (
    os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    or _default_webhook_secret(TELEGRAM_BOT_TOKEN)
)

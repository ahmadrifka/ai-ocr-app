import os
from dotenv import load_dotenv

load_dotenv()


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").strip().lower()
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
FILESTORE_PATH: str = os.getenv("FILESTORE_PATH", "./filestore")
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./ocr.db")

# "production" refuses to start without dashboard/API credentials.
APP_ENV: str = os.getenv("APP_ENV", "development").strip().lower()

# Image storage: "local" (FILESTORE_PATH on disk) or "supabase" (Supabase Storage bucket).
STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local").strip().lower()
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY: str = os.getenv("SUPABASE_SECRET_KEY", "").strip()
SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "receipts").strip()

# Single-instance hosting (e.g. Render free tier) runs the OCR worker inside the API process.
RUN_WORKER_IN_API: bool = _env_flag("RUN_WORKER_IN_API")

# Authentication is enforced when at least one credential is configured.
DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "")
API_KEY: str = os.getenv("API_KEY", "").strip()
SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")
SESSION_MAX_AGE_SECONDS: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(7 * 24 * 3600)))

# Telegram webhook mode; Render exposes its public URL as RENDER_EXTERNAL_URL.
PUBLIC_BASE_URL: str = (
    os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
).rstrip("/")
TELEGRAM_WEBHOOK_ENABLED: bool = _env_flag("TELEGRAM_WEBHOOK_ENABLED")

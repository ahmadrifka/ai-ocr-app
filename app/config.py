import os
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").strip().lower()
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
FILESTORE_PATH: str = os.getenv("FILESTORE_PATH", "./filestore")
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./ocr.db")

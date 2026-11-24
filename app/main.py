import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import PUBLIC_BASE_URL, RUN_WORKER_IN_API, TELEGRAM_WEBHOOK_ENABLED
from app.database import async_session, init_db
from app.routers.auth import router as auth_router
from app.routers.documents import accounts_router, router as documents_router
from app.routers.telegram import router as telegram_router
from app.services.auth import is_authorized, requires_auth, validate_auth_config
from app.services.filestore import validate_storage_backend
from app.services.worker import worker_loop
from bot.webhook import TelegramWebhook


DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_auth_config()
    validate_storage_backend()
    await init_db()

    app.state.telegram_webhook = await _start_telegram_webhook()
    worker_task = asyncio.create_task(worker_loop(async_session)) if RUN_WORKER_IN_API else None
    try:
        yield
    finally:
        if app.state.telegram_webhook is not None:
            await app.state.telegram_webhook.stop()
        if worker_task is not None:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task


async def _start_telegram_webhook() -> TelegramWebhook | None:
    if not TELEGRAM_WEBHOOK_ENABLED:
        return None
    webhook = TelegramWebhook.from_config()
    await webhook.start(PUBLIC_BASE_URL)
    return webhook


app = FastAPI(
    title="AI OCR App",
    description="Upload images for queued LLM-powered transaction extraction and classification",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def enforce_authentication(request: Request, call_next):
    if requires_auth(request.url.path) and not is_authorized(request):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return await call_next(request)


app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(accounts_router)
app.include_router(telegram_router)
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")


@app.get("/health")
async def health():
    return {"status": "ok"}

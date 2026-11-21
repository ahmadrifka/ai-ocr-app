from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers.documents import accounts_router, router as documents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="AI OCR App",
    description="Upload images for queued LLM-powered transaction extraction and classification",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(documents_router)
app.include_router(accounts_router)
app.mount(
    "/dashboard",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "dashboard", html=True),
    name="dashboard",
)


@app.get("/health")
async def health():
    return {"status": "ok"}

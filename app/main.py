from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import init_db
from app.routers.documents import router as documents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="AI OCR App",
    description="Upload images → LLM-powered transaction extraction, classification, and storage",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(documents_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

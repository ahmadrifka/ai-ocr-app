import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import OcrJob, Transaction
from app.schemas import DocumentOut, UploadAccepted, UploadStatusOut
from app.services.uploads import create_upload_job


router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/tiff"}


@router.post("/upload", response_model=UploadAccepted, status_code=202)
async def upload_document(
    response: Response,
    file: UploadFile = File(...),
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=255
    ),
    db: AsyncSession = Depends(get_db),
):
    """Save an image and enqueue OCR without waiting for the LLM."""
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {', '.join(sorted(ALLOWED_MIME))}",
        )

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 20 MB limit")

    idempotency_key = idempotency_key.strip()
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key cannot be blank")

    job = await create_upload_job(
        db,
        filename=file.filename or "upload.bin",
        content_type=file.content_type,
        content=content,
        idempotency_key=idempotency_key,
    )
    status_url = f"/api/documents/uploads/{job.upload_id}"
    response.headers["Location"] = status_url
    return UploadAccepted(
        upload_id=job.upload_id,
        status=job.status,
        status_url=status_url,
    )


@router.get("/uploads/{upload_id}", response_model=UploadStatusOut)
async def get_upload_status(
    upload_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(OcrJob, upload_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return UploadStatusOut(
        upload_id=job.upload_id,
        status=job.status,
        attempt_count=job.attempt_count,
        transaction_record_id=job.transaction_record_id,
    )


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    skip: int = 0,
    limit: int = 20,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List stored transactions with optional category filter."""
    stmt = select(Transaction).order_by(Transaction.created_at.desc())
    if category:
        stmt = stmt.where(Transaction.category == category)
    stmt = stmt.offset(skip).limit(limit)
    rows = await db.execute(stmt)
    return rows.scalars().all()


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single transaction by ID."""
    doc = await db.get(Transaction, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return doc

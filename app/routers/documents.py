import mimetypes
from pathlib import PurePosixPath
import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import OcrJob, Transaction, accounts_table
from app.schemas import (
    AccountCreate,
    AccountDelete,
    AccountOut,
    AccountUpdate,
    DocumentOut,
    TransactionUpdate,
    UploadAccepted,
    UploadJobOut,
    UploadStatusOut,
)
from app.services.dedupe import IMAGE_DEDUPE_KEY_PREFIX, transaction_dedupe_key
from app.services.filestore import read_file
from app.services.ocr_guardrails import review_flags
from app.services.uploads import create_upload_job


router = APIRouter(prefix="/api/documents", tags=["documents"])
accounts_router = APIRouter(prefix="/api/accounts", tags=["accounts"])

ALLOWED_MIME = {"image/jpeg", "image/jpg"}


@accounts_router.get("", response_model=list[AccountOut])
async def list_accounts(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(
            accounts_table.c.account_number,
            accounts_table.c.account_name,
            accounts_table.c.bank_name,
        ).order_by(accounts_table.c.bank_name, accounts_table.c.account_name)
    )
    return [dict(row) for row in rows.mappings().all()]


@accounts_router.patch("", response_model=AccountOut)
async def update_account(payload: AccountUpdate, db: AsyncSession = Depends(get_db)):
    current = (
        payload.current_account_number,
        payload.current_account_name,
        payload.current_bank_name,
    )
    columns = (
        accounts_table.c.account_number,
        accounts_table.c.account_name,
        accounts_table.c.bank_name,
    )
    conditions = [column.is_not_distinct_from(value) for column, value in zip(columns, current)]
    matches = (
        await db.execute(select(*columns).where(*conditions).with_for_update())
    ).mappings().all()
    if not matches:
        raise HTTPException(status_code=404, detail="Account not found")
    if len(matches) != 1:
        raise HTTPException(
            status_code=409,
            detail="Account identity is ambiguous; account rows need unique identifiers to edit safely",
        )

    new_values = {
        "account_number": payload.account_number.strip(),
        "account_name": payload.account_name.strip(),
        "bank_name": payload.bank_name.strip(),
    }
    if not all(new_values.values()):
        raise HTTPException(status_code=422, detail="Account fields cannot be blank")
    result = await db.execute(update(accounts_table).where(*conditions).values(**new_values))
    if getattr(result, "rowcount", None) != 1:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="Account changed while you were editing; refresh and retry"
        )
    await db.commit()
    return new_values


@accounts_router.post("", response_model=AccountOut, status_code=201)
async def create_account(payload: AccountCreate, db: AsyncSession = Depends(get_db)):
    new_values = {
        "account_number": payload.account_number.strip(),
        "account_name": payload.account_name.strip(),
        "bank_name": payload.bank_name.strip(),
    }
    if not all(new_values.values()):
        raise HTTPException(status_code=422, detail="Account fields cannot be blank")
    await db.execute(accounts_table.insert().values(**new_values))
    await db.commit()
    return new_values


@accounts_router.delete("", status_code=204)
async def delete_account(payload: AccountDelete, db: AsyncSession = Depends(get_db)):
    columns = (
        accounts_table.c.account_number,
        accounts_table.c.account_name,
        accounts_table.c.bank_name,
    )
    values = (payload.account_number, payload.account_name, payload.bank_name)
    conditions = [column.is_not_distinct_from(value) for column, value in zip(columns, values)]
    matches = (
        await db.execute(select(*columns).where(*conditions).with_for_update())
    ).mappings().all()
    if not matches:
        raise HTTPException(status_code=404, detail="Account not found")
    if len(matches) != 1:
        raise HTTPException(
            status_code=409,
            detail="Account identity is ambiguous; account rows need unique identifiers to delete safely",
        )
    await db.execute(delete(accounts_table).where(*conditions))
    await db.commit()
    return Response(status_code=204)


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
        ai_analysis_duration_ms=job.ai_analysis_duration_ms,
        transaction_record_id=job.transaction_record_id,
        last_error=job.last_error,
    )


@router.get("/uploads", response_model=list[UploadJobOut])
async def list_uploads(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """List recent OCR jobs for the local dashboard."""
    stmt = (
        select(OcrJob)
        .order_by(OcrJob.created_at.desc(), OcrJob.upload_id.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = await db.scalars(stmt)
    return rows.all()


@router.get("/uploads/{upload_id}/image")
async def get_upload_image(upload_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Serve the image attached to an OCR upload job, if it still exists."""
    job = await db.get(OcrJob, upload_id)
    if job is None or not job.asset_path:
        raise HTTPException(status_code=404, detail="Upload image not found")

    try:
        content = await read_file(job.asset_path)
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Upload image not found") from None

    media_type = job.content_type if job.content_type in ALLOWED_MIME else "application/octet-stream"
    return _inline_image_response(content, job.asset_path, media_type)


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
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


@router.patch("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: int,
    payload: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Transaction, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one transaction field is required")
    for required_field in ("description", "category", "sub_category", "transaction_type"):
        if required_field in changes and changes[required_field] is None:
            raise HTTPException(status_code=422, detail=f"{required_field} cannot be null")

    for field, value in changes.items():
        setattr(document, field, value)
    if "description" in changes:
        document.review_flags = review_flags(document.description)
    if {"source_bank", "transaction_id", "amount", "transaction_date"} & changes.keys():
        updated_dedupe_key = transaction_dedupe_key(
            document.source_bank,
            document.transaction_id,
            document.amount,
            document.transaction_date,
        )
        preserves_image_key = (
            updated_dedupe_key is None
            and (document.dedupe_key or "").startswith(IMAGE_DEDUPE_KEY_PREFIX)
        )
        if not preserves_image_key:
            document.dedupe_key = updated_dedupe_key

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="This edit conflicts with an existing transaction"
        ) from None
    await db.refresh(document)
    return document


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single transaction by ID."""
    doc = await db.get(Transaction, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return doc


@router.get("/{document_id}/receipt")
async def get_document_receipt(document_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the receipt image attached to a transaction, if it still exists."""
    doc = await db.get(Transaction, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if not doc.asset_path:
        raise HTTPException(status_code=404, detail="Receipt image not found")

    try:
        content = await read_file(doc.asset_path)
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Receipt image not found") from None

    media_type = mimetypes.guess_type(doc.asset_path)[0] or "application/octet-stream"
    return _inline_image_response(content, doc.asset_path, media_type)


def _inline_image_response(content: bytes, asset_path: str, media_type: str) -> Response:
    filename = PurePosixPath(asset_path).name
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )

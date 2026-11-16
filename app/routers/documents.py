from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Transaction
from app.schemas import DocumentOut
from app.services.accounts import beneficiary_is_account
from app.services.filestore import save_file
from app.services.llm import analyze_image

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/tiff"}


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image → extract transaction fields → save to DB and filestore."""
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {', '.join(sorted(ALLOWED_MIME))}",
        )

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 20 MB limit")

    # Save to filestore
    filepath = await save_file(file.filename or "upload.bin", content)

    # Analyze with LLM
    try:
        result = await analyze_image(content, file.content_type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM analysis failed: {exc}")

    # Classify incoming transfers to one of our registered bank accounts.
    incoming = await beneficiary_is_account(db, result)

    # Persist to database
    doc = Transaction(
        transaction_date=result.transaction_date,
        description=result.description,
        category="sale" if incoming else result.category,
        transaction_type="INCOMING" if incoming else result.transaction_type,
        beneficiary_bank=result.beneficiary_bank,
        beneficiary_account_number=result.beneficiary_account_number,
        benecifiacry_account_name=result.benecifiacry_account_name,
        source_bank=result.source_bank,
        source_account_number=result.source_account_number,
        source_account_name=result.source_account_name,
        amount=result.amount,
        asset_path=filepath,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return doc


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

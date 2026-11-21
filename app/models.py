import datetime as dt
from decimal import Decimal
import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Table, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


accounts_table = Table(
    "accounts",
    Base.metadata,
    Column("account_number", Text),
    Column("account_name", Text),
    Column("bank_name", Text),
)


class Transaction(Base):
    __tablename__ = "transaction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    transaction_date: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="Uncategorized")
    transaction_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="EXPENSES"
    )
    beneficiary_bank: Mapped[str | None] = mapped_column(String(255), nullable=True)
    beneficiary_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    benecifiacry_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_bank: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_account_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    asset_path: Mapped[str] = mapped_column(String(500), nullable=False)


Index("transaction_dedupe_key_uq", Transaction.dedupe_key, unique=True)


class OcrJob(Base):
    __tablename__ = "ocr_upload_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'DUPLICATE', 'FAILED')",
            name="ocr_upload_job_status_check",
        ),
        CheckConstraint("attempt_count >= 0", name="ocr_upload_job_attempt_count_check"),
    )

    upload_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    asset_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_analysis_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lease_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("transaction.id", ondelete="SET NULL"), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


Index("ocr_upload_job_pickup_idx", OcrJob.status, OcrJob.available_at)
Index("ocr_upload_job_duplicate_cleanup_idx", OcrJob.status, OcrJob.asset_path)

import datetime as dt
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


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
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
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

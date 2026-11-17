import datetime as dt
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


ExpenseCategory = Literal[
    "Bahan Baku",
    "Biaya-Gaji Karyawan",
    "Biaya-Konsumsi",
    "Biaya-Perlengkapan Kantor dan Administrasi",
    "Biaya-Transportasi",
    "Biaya-Ongkir",
    "Biaya-Perbaikan Bangunan",
    "Biaya-Operasional",
    "Biaya-Pembelian Aset",
    "Biaya-Sosial",
    "Uncategorized",
]
TransactionCategory = ExpenseCategory | Literal["sale"]


class DocumentOut(BaseModel):
    id: int
    created_at: dt.datetime
    updated_at: dt.datetime
    transaction_date: dt.datetime | None
    transaction_id: str | None
    description: str
    category: TransactionCategory
    transaction_type: Literal["EXPENSES", "INCOMING"]
    beneficiary_bank: str | None
    beneficiary_account_number: str | None
    benecifiacry_account_name: str | None
    source_bank: str | None
    source_account_number: str | None
    source_account_name: str | None
    amount: Decimal | None
    asset_path: str

    model_config = ConfigDict(from_attributes=True)


class AnalysisResult(BaseModel):
    transaction_date: dt.datetime | None = None
    transaction_id: str | None = None
    description: str
    category: ExpenseCategory
    transaction_type: Literal["EXPENSES"]
    beneficiary_bank: str | None = None
    beneficiary_account_number: str | None = None
    benecifiacry_account_name: str | None = None
    source_bank: str | None = None
    source_account_number: str | None = None
    source_account_name: str | None = None
    amount: Decimal | None = None


class UploadAccepted(BaseModel):
    upload_id: UUID
    status: str
    status_url: str


class UploadStatusOut(BaseModel):
    upload_id: UUID
    status: str
    attempt_count: int
    transaction_record_id: int | None

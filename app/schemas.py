import datetime as dt
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool


TransactionType = Literal["EXPENSES", "INCOMING", "TRANSFER"]

Category = Literal[
    "Persediaan",
    "Penjualan",
    "Modal dan Prive",
    "Beban Operasional",
    "Utang/Piutang",
    "Aset Tetap/Investasi",
    "Pendapatan/Beban Lain",
    "Pajak",
    "Uncategorized",
]

SubCategory = Literal[
    "Bahan Baku",
    "Penjualan Produk",
    "Modal",
    "Prive",
    "Biaya-Gaji Karyawan",
    "Biaya-Konsumsi",
    "Biaya-Perlengkapan Kantor dan Administrasi",
    "Biaya-Transportasi",
    "Biaya-Ongkir",
    "Biaya-Perbaikan Bangunan",
    "Biaya-Operasional",
    "Biaya-Sosial",
    "Utang",
    "Piutang",
    "Biaya-Pembelian Aset",
    "Beban Lain",
    "Pendapatan Lain",
    "Pembayaran pajak",
    "Uncategorized",
]


class DocumentOut(BaseModel):
    id: int
    created_at: dt.datetime
    updated_at: dt.datetime
    transaction_date: dt.datetime | None
    transaction_id: str | None
    description: str
    category: Category
    sub_category: SubCategory
    review_flags: list[str]
    transaction_type: TransactionType
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
    model_config = ConfigDict(extra="forbid")

    is_receipt: StrictBool
    transaction_date: dt.datetime | None = None
    transaction_id: str | None = None
    description: str
    category: Category
    sub_category: SubCategory
    transaction_type: Literal["EXPENSES"]
    beneficiary_bank: str | None = None
    beneficiary_account_number: str | None = None
    benecifiacry_account_name: str | None = None
    source_bank: str | None = None
    source_account_number: str | None = None
    source_account_name: str | None = None
    amount: Decimal | None = Field(default=None, ge=0)


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_date: dt.datetime | None = None
    transaction_id: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    category: Category | None = None
    sub_category: SubCategory | None = None
    transaction_type: TransactionType | None = None
    beneficiary_bank: str | None = Field(default=None, max_length=255)
    beneficiary_account_number: str | None = Field(default=None, max_length=100)
    benecifiacry_account_name: str | None = Field(default=None, max_length=255)
    source_bank: str | None = Field(default=None, max_length=255)
    source_account_number: str | None = Field(default=None, max_length=100)
    source_account_name: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(default=None, ge=0)


class AccountOut(BaseModel):
    account_number: str | None
    account_name: str | None
    bank_name: str | None


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_account_number: str | None
    current_account_name: str | None
    current_bank_name: str | None
    account_number: str = Field(min_length=1, max_length=100)
    account_name: str = Field(min_length=1, max_length=255)
    bank_name: str = Field(min_length=1, max_length=255)


class UploadAccepted(BaseModel):
    upload_id: UUID
    status: str
    status_url: str


class UploadStatusOut(BaseModel):
    upload_id: UUID
    status: str
    attempt_count: int
    ai_analysis_duration_ms: int | None
    transaction_record_id: int | None
    last_error: str | None


class UploadJobOut(BaseModel):
    upload_id: UUID
    status: Literal["PENDING", "PROCESSING", "COMPLETED", "DUPLICATE", "FAILED"]
    attempt_count: int
    ai_analysis_duration_ms: int | None
    content_type: str
    created_at: dt.datetime
    transaction_record_id: int | None
    last_error: str | None

    model_config = ConfigDict(from_attributes=True)

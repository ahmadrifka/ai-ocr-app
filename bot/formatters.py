"""Formatters for Telegram bot responses."""

from decimal import Decimal
from typing import Any


def format_currency(amount: Any) -> str:
    """Format numeric amount into standard IDR string."""
    if amount is None:
        return "Tidak tertera"
    try:
        val = Decimal(str(amount))
        formatted = f"{val:,.2f}"
        parts = formatted.split(".")
        int_part = parts[0].replace(",", ".")
        dec_part = parts[1]
        if dec_part == "00":
            return f"Rp {int_part}"
        return f"Rp {int_part},{dec_part}"
    except Exception:
        return str(amount)


def format_transaction_success(doc: dict[str, Any]) -> str:
    """Format extracted transaction details into an informative Telegram message."""
    amount_str = format_currency(doc.get("amount"))
    date_str = doc.get("transaction_date") or "Tidak tertera"
    if date_str and "T" in str(date_str):
        date_str = str(date_str).replace("T", " ")
        if "+" in date_str:
            date_str = date_str.split("+")[0]

    category = doc.get("category") or "Uncategorized"
    description = doc.get("description") or "-"
    tx_type = doc.get("transaction_type") or "EXPENSES"
    tx_id = doc.get("transaction_id") or "Tidak tertera"
    source_bank = doc.get("source_bank") or "-"
    source_acc = doc.get("source_account_number") or "-"
    dest_bank = doc.get("beneficiary_bank") or "-"
    dest_acc = doc.get("beneficiary_account_number") or "-"
    dest_name = doc.get("benecifiacry_account_name") or "-"

    flags = doc.get("review_flags") or []
    flag_notice = ""
    if flags:
        flag_notice = f"\n⚠️ <b>Catatan Review:</b> {', '.join(flags)}"

    return (
        "✅ <b>Struk Berhasil Diekstrak & Dicatat!</b>\n\n"
        f"💰 <b>Nominal:</b> {amount_str}\n"
        f"🏷️ <b>Kategori:</b> {category}\n"
        f"📝 <b>Keterangan:</b> {description}\n"
        f"📅 <b>Waktu Transaksi:</b> {date_str}\n"
        f"🔢 <b>No. Referensi / ID:</b> {tx_id}\n"
        f"💳 <b>Tipe Transaksi:</b> {tx_type}\n\n"
        "🏛️ <b>Detail Rekening:</b>\n"
        f"• Asal: {source_bank} ({source_acc})\n"
        f"• Tujuan: {dest_bank} ({dest_acc} a.n. {dest_name})"
        f"{flag_notice}\n\n"
        f"<i>Tersimpan di database (ID: #{doc.get('id')})</i>"
    )


def format_duplicate_notice(doc: dict[str, Any]) -> str:
    """Format duplicate transaction notification."""
    amount_str = format_currency(doc.get("amount"))
    date_str = doc.get("transaction_date") or "-"
    return (
        "ℹ️ <b>Struk / Transaksi Ini Sudah Pernah Dicatat (Duplikat)</b>\n\n"
        "Transaksi dengan referensi atau gambar yang sama telah tersimpan sebelumnya.\n"
        f"• <b>ID Database:</b> #{doc.get('id', '-')}\n"
        f"• <b>Nominal:</b> {amount_str}\n"
        f"• <b>Kategori:</b> {doc.get('category') or '-'}\n"
        f"• <b>Tanggal:</b> {date_str}\n"
    )


def format_ocr_failure(error_msg: str | None = None) -> str:
    """Format failure message."""
    details = f"\nDetail: <i>{error_msg}</i>" if error_msg else ""
    return (
        "❌ <b>Gagal Memproses Gambar / Struk</b>\n\n"
        "Gambar yang dikirim tidak dapat dibaca sebagai bukti transaksi atau terjadi kendala pemrosesan OCR.\n"
        f"{details}\n\n"
        "💡 <i>Tips: Pastikan foto struk terlihat jelas, tidak buram, dan teks transaksi terbaca dengan baik.</i>"
    )

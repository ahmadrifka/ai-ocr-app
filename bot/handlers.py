"""Telegram bot message and command handlers."""

import io
import logging
import time
from PIL import Image
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.client import OcrApiClient
from bot.config import (
    ALLOWED_TELEGRAM_USER_IDS,
    BOT_POLL_INTERVAL_SECONDS,
    BOT_POLL_TIMEOUT_SECONDS,
    OCR_API_BASE_URL,
    OCR_API_KEY,
)
from bot.formatters import (
    format_duplicate_notice,
    format_ocr_failure,
    format_transaction_success,
)
from bot.keyboards import (
    CATEGORIES,
    CATEGORY_HIERARCHY,
    build_category_keyboard,
    build_confirmation_keyboard,
    build_subcategory_keyboard,
)

logger = logging.getLogger(__name__)
ocr_client = OcrApiClient(OCR_API_BASE_URL, OCR_API_KEY)
from telegram.ext import ApplicationHandlerStop


async def whitelist_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Silent drop updates from unauthorized users if whitelist is configured."""
    if not ALLOWED_TELEGRAM_USER_IDS:
        return

    user = update.effective_user
    user_id = user.id if user else None
    if user_id not in ALLOWED_TELEGRAM_USER_IDS:
        username = f"@{user.username}" if user and user.username else "no-username"
        logger.warning(
            "[UNAUTHORIZED ACCESS DROPPED] User ID %s (%s) attempted action. Silent drop applied.",
            user_id,
            username,
        )
        raise ApplicationHandlerStop



async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message with instructions."""
    if not update.effective_message:
        return

    welcome_text = (
        "Halo! Saya <b>LokalityBot</b> 🤖\n\n"
        "Silakan kirim foto atau dokumen bukti transfer / struk belanja Anda ke sini. "
        "Sistem akan mengekstrak rincian transaksi secara otomatis (nominal, kategori, tanggal, bank/rekening) "
        "menggunakan AI OCR dan mencatatnya ke database keuangan.\n\n"
        "<b>Perintah yang tersedia:</b>\n"
        "• /start - Mulai interaksi\n"
        "• /help - Panduan penggunaan\n"
        "• /status - Cek status service backend & OCR engine\n\n"
        "<i>Silakan kirimkan foto struk Anda sekarang.</i>"
    )
    await update.effective_message.reply_text(welcome_text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help information."""
    if not update.effective_message:
        return

    help_text = (
        "<b>📖 Panduan Penggunaan LokalityBot</b>\n\n"
        "1. <b>Kirim Foto Struk:</b> Ambil foto atau screenshot bukti transfer / struk belanja.\n"
        "2. <b>Format yang didukung:</b> JPEG, PNG, WebP, GIF, TIFF.\n"
        "3. <b>Tips Hasil Terbaik:</b>\n"
        "   • Pastikan teks terbaca jelas dan tidak buram.\n"
        "   • Pastikan nominal, tanggal, dan nama bank/rekening terlihat utuh.\n"
        "4. <b>Deduplikasi Otomatis:</b> Struk yang sama tidak akan tercatat ganda di database.\n\n"
        "Jika ada kendala, hubungi tim developer backend / devops."
    )
    await update.effective_message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check health status of backend OCR service."""
    if not update.effective_message:
        return

    is_healthy = await ocr_client.check_health()
    if is_healthy:
        msg = (
            "✅ <b>Service Status: ONLINE</b>\n\n"
            f"Backend API ({OCR_API_BASE_URL}) terhubung dan siap memproses transaksi."
        )
    else:
        msg = (
            "⚠️ <b>Service Status: OFFLINE / UNREACHABLE</b>\n\n"
            f"Backend API di {OCR_API_BASE_URL} tidak dapat dijangkau.\n"
            "Mohon pastikan service FastAPI sudah berjalan."
        )
    await update.effective_message.reply_text(msg, parse_mode=ParseMode.HTML)


def _normalize_image_to_jpeg(raw_bytes: bytes) -> tuple[bytes, str, str]:
    """Normalize any image bytes to standard JPEG format."""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            rgb = img.convert("RGB")
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=92)
            return out.getvalue(), "receipt.jpg", "image/jpeg"
    except Exception as exc:
        logger.warning("Image normalization failed, falling back to raw: %s", exc)
        return raw_bytes, "receipt.jpg", "image/jpeg"


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photo messages."""
    msg = update.effective_message
    if not msg or not msg.photo:
        return

    status_msg = await msg.reply_text(
        "⏳ <i>Menerima foto struk, mengunggah ke engine AI OCR...</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        photo_obj = msg.photo[-1]
        file = await photo_obj.get_file()
        byte_data = await file.download_as_bytearray()
        image_bytes, filename, content_type = _normalize_image_to_jpeg(bytes(byte_data))

        idempotency_key = f"tg-{msg.chat_id}-{msg.message_id}-{int(time.time())}"
        upload_job = await ocr_client.upload_document(
            file_bytes=image_bytes,
            filename=filename,
            content_type=content_type,
            idempotency_key=idempotency_key,
        )
        upload_id = upload_job.get("upload_id")
        if not upload_id:
            await status_msg.edit_text(
                format_ocr_failure("Upload ID tidak diterima dari backend service"),
                parse_mode=ParseMode.HTML,
            )
            return

        await status_msg.edit_text(
            "⏳ <i>Sedang membaca & mengekstrak data transaksi dengan LLM Vision...</i>",
            parse_mode=ParseMode.HTML,
        )

        status, doc, error_msg = await ocr_client.poll_until_complete(
            upload_id=str(upload_id),
            poll_interval=BOT_POLL_INTERVAL_SECONDS,
            timeout=BOT_POLL_TIMEOUT_SECONDS,
        )

        if status == "COMPLETED" and doc:
            tx_id = doc.get("id")
            tx_type = doc.get("transaction_type")
            keyboard = build_confirmation_keyboard(tx_id, tx_type=tx_type) if tx_id else None
            await status_msg.edit_text(
                format_transaction_success(doc),
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        elif status == "DUPLICATE" and doc:
            await status_msg.edit_text(format_duplicate_notice(doc), parse_mode=ParseMode.HTML)
        elif status == "FAILED":
            await status_msg.edit_text(format_ocr_failure(error_msg), parse_mode=ParseMode.HTML)
        else:
            await status_msg.edit_text(
                "⏳ <i>Struk telah diterima dan antrean OCR masih berjalan di worker.</i>\n"
                f"ID Unggahan: <code>{upload_id}</code>\nStatus saat ini: <b>{status}</b>",
                parse_mode=ParseMode.HTML,
            )
    except Exception as exc:
        logger.exception("Error handling photo receipt: %s", exc)
        await status_msg.edit_text(
            format_ocr_failure(f"Terjadi kesalahan sistem: {str(exc)}"),
            parse_mode=ParseMode.HTML,
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming document files (uncompressed images)."""
    msg = update.effective_message
    if not msg or not msg.document:
        return

    doc_obj = msg.document
    mime = (doc_obj.mime_type or "").lower()
    name = (doc_obj.file_name or "").lower()

    is_image = mime.startswith("image/") or any(
        name.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff")
    )

    if not is_image:
        await msg.reply_text(
            "⚠️ <b>Format file tidak didukung.</b>\n\n"
            "Mohon kirimkan gambar bukti struk dalam format <b>JPEG, PNG, WebP, atau GIF</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    status_msg = await msg.reply_text(
        "⏳ <i>Menerima dokumen gambar, mengunggah ke engine AI OCR...</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        file = await doc_obj.get_file()
        byte_data = await file.download_as_bytearray()
        image_bytes, filename, content_type = _normalize_image_to_jpeg(bytes(byte_data))

        idempotency_key = f"tg-{msg.chat_id}-{msg.message_id}-{int(time.time())}"
        upload_job = await ocr_client.upload_document(
            file_bytes=image_bytes,
            filename=filename,
            content_type=content_type,
            idempotency_key=idempotency_key,
        )
        upload_id = upload_job.get("upload_id")
        if not upload_id:
            await status_msg.edit_text(
                format_ocr_failure("Upload ID tidak diterima dari backend service"),
                parse_mode=ParseMode.HTML,
            )
            return

        await status_msg.edit_text(
            "⏳ <i>Sedang membaca & mengekstrak data transaksi dengan LLM Vision...</i>",
            parse_mode=ParseMode.HTML,
        )

        status, doc, error_msg = await ocr_client.poll_until_complete(
            upload_id=str(upload_id),
            poll_interval=BOT_POLL_INTERVAL_SECONDS,
            timeout=BOT_POLL_TIMEOUT_SECONDS,
        )

        if status == "COMPLETED" and doc:
            tx_id = doc.get("id")
            tx_type = doc.get("transaction_type")
            keyboard = build_confirmation_keyboard(tx_id, tx_type=tx_type) if tx_id else None
            await status_msg.edit_text(
                format_transaction_success(doc),
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        elif status == "DUPLICATE" and doc:
            await status_msg.edit_text(format_duplicate_notice(doc), parse_mode=ParseMode.HTML)
        elif status == "FAILED":
            await status_msg.edit_text(format_ocr_failure(error_msg), parse_mode=ParseMode.HTML)
        else:
            await status_msg.edit_text(
                "⏳ <i>Struk telah diterima dan antrean OCR masih berjalan di worker.</i>\n"
                f"ID Unggahan: <code>{upload_id}</code>\nStatus saat ini: <b>{status}</b>",
                parse_mode=ParseMode.HTML,
            )
    except Exception as exc:
        logger.exception("Error handling document receipt: %s", exc)
        await status_msg.edit_text(
            format_ocr_failure(f"Terjadi kesalahan sistem: {str(exc)}"),
            parse_mode=ParseMode.HTML,
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guide users when they send non-command text."""
    if not update.effective_message:
        return
    await update.effective_message.reply_text(
        "Kirim foto atau file struk transfer / belanja untuk mencatat transaksi secara otomatis! 📸\n\n"
        "Gunakan /help untuk melihat panduan lengkap.",
        parse_mode=ParseMode.HTML,
    )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive inline keyboard button clicks for transaction confirmation and category editing."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    logger.info("Received callback query: %s from user: %s", data, query.from_user.id if query.from_user else None)

    try:
        parts = data.split(":")
        action = parts[0]

        if action == "tx_confirm":
            tx_id = int(parts[1])
            await query.answer("Transaksi berhasil dikonfirmasi dan dikunci! ✅")
            try:
                doc = await ocr_client.get_document(tx_id)
            except Exception:
                doc = {"id": tx_id}

            updated_text = format_transaction_success(doc, status_label="Terkonfirmasi (Sesuai) [Terkunci] 🔒")
            await query.edit_message_text(
                text=updated_text,
                parse_mode=ParseMode.HTML,
                reply_markup=None,
            )

        elif action == "tx_edit":
            tx_id = int(parts[1])
            tx_type = parts[2] if len(parts) > 2 else None
            await query.answer()

            if not tx_type:
                try:
                    doc = await ocr_client.get_document(tx_id)
                    tx_type = doc.get("transaction_type")
                except Exception as exc:
                    logger.warning("Could not fetch doc for tx_edit: %s", exc)

            cat_keyboard = build_category_keyboard(tx_id, tx_type=tx_type)
            type_label = f" ({tx_type})" if tx_type else ""
            edit_text = (
                f"✏️ <b>Edit Kategori Transaksi (ID: #{tx_id}{type_label})</b>\n\n"
                "Silakan pilih <b>Kategori</b> yang sesuai:"
            )
            await query.edit_message_text(
                text=edit_text,
                parse_mode=ParseMode.HTML,
                reply_markup=cat_keyboard,
            )

        elif action == "tx_cat":
            tx_id = int(parts[1])
            cat_idx = int(parts[2])
            tx_type = parts[3] if len(parts) > 3 else None

            if cat_idx < 0 or cat_idx >= len(CATEGORIES):
                await query.answer("Kategori tidak valid.", show_alert=True)
                return

            cat_name = CATEGORIES[cat_idx]
            await query.answer()

            if not tx_type:
                try:
                    doc = await ocr_client.get_document(tx_id)
                    tx_type = doc.get("transaction_type")
                except Exception:
                    pass

            sub_keyboard = build_subcategory_keyboard(tx_id, cat_idx, tx_type=tx_type)
            type_label = f" ({tx_type})" if tx_type else ""
            sub_text = (
                f"🏷️ <b>Kategori Dipilih:</b> {cat_name}\n"
                f"🔢 <b>ID Transaksi:</b> #{tx_id}{type_label}\n\n"
                "Silakan pilih <b>Sub Kategori</b>:"
            )
            await query.edit_message_text(
                text=sub_text,
                parse_mode=ParseMode.HTML,
                reply_markup=sub_keyboard,
            )

        elif action == "tx_sub":
            tx_id = int(parts[1])
            cat_idx = int(parts[2])
            sub_idx = int(parts[3])

            if cat_idx < 0 or cat_idx >= len(CATEGORIES):
                await query.answer("Kategori tidak valid.", show_alert=True)
                return

            cat_name = CATEGORIES[cat_idx]
            full_subcategories = CATEGORY_HIERARCHY.get(cat_name, [])
            if sub_idx < 0 or sub_idx >= len(full_subcategories):
                await query.answer("Sub kategori tidak valid.", show_alert=True)
                return

            sub_name = full_subcategories[sub_idx]
            await query.answer("Memperbarui kategori transaksi...")

            try:
                updated_doc = await ocr_client.update_document(
                    tx_id,
                    {"category": cat_name, "sub_category": sub_name},
                )
                final_text = format_transaction_success(
                    updated_doc,
                    status_label=f"Kategori Diperbarui ({cat_name} / {sub_name}) & Terkonfirmasi 🔒",
                )
                await query.edit_message_text(
                    text=final_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                )
            except Exception as exc:
                logger.exception("Failed to update transaction #%s: %s", tx_id, exc)
                await query.answer(f"Gagal memperbarui transaksi: {str(exc)}", show_alert=True)

        elif action == "tx_back":
            tx_id = int(parts[1])
            await query.answer()
            try:
                doc = await ocr_client.get_document(tx_id)
                tx_type = doc.get("transaction_type")
                await query.edit_message_text(
                    text=format_transaction_success(doc),
                    parse_mode=ParseMode.HTML,
                    reply_markup=build_confirmation_keyboard(tx_id, tx_type=tx_type),
                )
            except Exception as exc:
                logger.warning("Could not fetch doc for back action: %s", exc)
                await query.answer("Gagal memuat data transaksi.", show_alert=True)

        else:
            await query.answer("Perintah tidak dikenal.")

    except Exception as exc:
        logger.exception("Error handling callback query: %s", exc)
        try:
            await query.answer("Terjadi kesalahan sistem saat memproses tombol.", show_alert=True)
        except Exception:
            pass

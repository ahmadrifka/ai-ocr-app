import io
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from PIL import Image
from telegram.constants import ParseMode

from bot.client import OcrApiClient
from bot.formatters import (
    REVIEW_FLAG_LABELS,
    TRANSACTION_TYPE_LABELS,
    format_currency,
    format_duplicate_notice,
    format_ocr_failure,
    format_review_flag,
    format_transaction_success,
    format_transaction_type,
)
from bot.handlers import (
    _normalize_image_to_jpeg,
    handle_callback_query,
    help_command,
    start_command,
    status_command,
)
from bot.keyboards import (
    CATEGORIES,
    CATEGORY_HIERARCHY,
    build_category_keyboard,
    build_confirmation_keyboard,
    build_subcategory_keyboard,
)
from bot.main import build_bot_app


class TestFormatters(unittest.TestCase):
    def test_format_currency_standard(self):
        self.assertEqual(format_currency(150000), "Rp 150.000")
        self.assertEqual(format_currency("2500000.50"), "Rp 2.500.000,50")
        self.assertEqual(format_currency(None), "Tidak tertera")

    def test_format_transaction_success(self):
        doc = {
            "id": 42,
            "amount": 75000,
            "transaction_date": "2026-11-22T10:30:00+07:00",
            "category": "Biaya-Konsumsi",
            "description": "Makan siang tim engineering",
            "transaction_type": "EXPENSES",
            "transaction_id": "TRX-998877",
            "source_bank": "BCA",
            "source_account_number": "1234567890",
            "beneficiary_bank": "Mandiri",
            "beneficiary_account_number": "0987654321",
            "benecifiacry_account_name": "Warung Berkah",
            "review_flags": ["high_amount_check"],
        }
        msg = format_transaction_success(doc)
        self.assertIn("Rp 75.000", msg)
        self.assertIn("Biaya-Konsumsi", msg)
        self.assertIn("Makan siang tim engineering", msg)
        self.assertIn("TRX-998877", msg)
        self.assertIn("high_amount_check", msg)
        self.assertIn("#42", msg)
        self.assertIn("Uang Keluar", msg)

    def test_format_transaction_type_mapping(self):
        self.assertEqual(format_transaction_type("EXPENSES"), "Uang Keluar")
        self.assertEqual(format_transaction_type("EXPENSE"), "Uang Keluar")
        self.assertEqual(format_transaction_type("INCOMING"), "Uang Masuk")
        self.assertEqual(format_transaction_type("TRANSFER"), "Transfer")
        self.assertEqual(format_transaction_type("expenses"), "Uang Keluar")
        self.assertEqual(format_transaction_type(None), "Uang Keluar")
        self.assertEqual(format_transaction_type("CUSTOM"), "CUSTOM")

    def test_format_transaction_success_types(self):
        doc_inc = {"id": 1, "amount": 1000, "transaction_type": "INCOMING"}
        self.assertIn("Uang Masuk", format_transaction_success(doc_inc))
        doc_trf = {"id": 2, "amount": 2000, "transaction_type": "TRANSFER"}
        self.assertIn("Transfer", format_transaction_success(doc_trf))

    def test_format_review_flag_mapping(self):
        self.assertEqual(format_review_flag("abusive_language"), "Bahasa tidak pantas")
        self.assertEqual(format_review_flag("sensitive_credentials_request"), "Permintaan kredensial / data rahasia")
        self.assertEqual(format_review_flag("urgent_payment_pressure"), "Desakan pembayaran mencurigakan")
        self.assertEqual(format_review_flag("instruction_like_content"), "Teks instruksi mencurigakan")
        self.assertEqual(format_review_flag("suspicious_wording"), "Kata-kata mencurigakan")
        self.assertEqual(format_review_flag("unmapped_flag"), "unmapped_flag")

    def test_format_transaction_success_with_mapped_review_flags(self):
        doc = {
            "id": 43,
            "amount": 100000,
            "review_flags": ["suspicious_wording", "urgent_payment_pressure"],
        }
        msg = format_transaction_success(doc)
        self.assertIn(
            "⚠️ <b>Catatan Review:</b> Kata-kata mencurigakan, Desakan pembayaran mencurigakan",
            msg,
        )

    def test_format_duplicate_notice(self):
        doc = {
            "id": 10,
            "amount": 50000,
            "transaction_date": "2026-11-20",
            "category": "Biaya-Ongkir",
        }
        msg = format_duplicate_notice(doc)
        self.assertIn("Duplikat", msg)
        self.assertIn("#10", msg)
        self.assertIn("Rp 50.000", msg)

    def test_format_ocr_failure(self):
        msg = format_ocr_failure("Teks tidak terbaca")
        self.assertIn("Gagal Memproses Gambar", msg)
        self.assertIn("Teks tidak terbaca", msg)


class TestImageNormalization(unittest.TestCase):
    def test_normalize_png_to_jpeg(self):
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        png_bytes = bio.getvalue()

        jpeg_bytes, filename, content_type = _normalize_image_to_jpeg(png_bytes)
        self.assertEqual(filename, "receipt.jpg")
        self.assertEqual(content_type, "image/jpeg")
        with Image.open(io.BytesIO(jpeg_bytes)) as result_img:
            self.assertEqual(result_img.format, "JPEG")


class TestOcrApiClient(unittest.IsolatedAsyncioTestCase):
    async def test_check_health_online(self):
        client = OcrApiClient("http://testserver")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp
            self.assertTrue(await client.check_health())

    async def test_check_health_offline(self):
        client = OcrApiClient("http://testserver")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.RequestError("Connection refused")
            self.assertFalse(await client.check_health())

    async def test_upload_document(self):
        client = OcrApiClient("http://testserver")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            mock_resp.json.return_value = {"upload_id": "test-uuid", "status": "PENDING"}
            mock_post.return_value = mock_resp

            res = await client.upload_document(b"fake-bytes", "receipt.jpg", "image/jpeg", "key-1")
            self.assertEqual(res["upload_id"], "test-uuid")
            mock_post.assert_called_once()

    async def test_poll_until_complete_success(self):
        client = OcrApiClient("http://testserver")
        with patch.object(client, "get_upload_status", new_callable=AsyncMock) as mock_status:
            with patch.object(client, "get_document", new_callable=AsyncMock) as mock_doc:
                mock_status.return_value = {
                    "status": "COMPLETED",
                    "transaction_record_id": 123,
                }
                mock_doc.return_value = {"id": 123, "amount": 50000}

                status, doc, err = await client.poll_until_complete("test-uuid", poll_interval=0.01, timeout=1.0)
                self.assertEqual(status, "COMPLETED")
                self.assertEqual(doc["id"], 123)
                self.assertIsNone(err)

    async def test_poll_until_complete_duplicate(self):
        client = OcrApiClient("http://testserver")
        with patch.object(client, "get_upload_status", new_callable=AsyncMock) as mock_status:
            with patch.object(client, "get_document", new_callable=AsyncMock) as mock_doc:
                mock_status.return_value = {
                    "status": "DUPLICATE",
                    "transaction_record_id": 99,
                }
                mock_doc.return_value = {"id": 99, "amount": 30000}

                status, doc, err = await client.poll_until_complete("test-uuid", poll_interval=0.01, timeout=1.0)
                self.assertEqual(status, "DUPLICATE")
                self.assertEqual(doc["id"], 99)
                self.assertIsNone(err)

    async def test_poll_until_complete_failed(self):
        client = OcrApiClient("http://testserver")
        with patch.object(client, "get_upload_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "status": "FAILED",
                "last_error": "Image corrupt or unreadable",
            }
            status, doc, err = await client.poll_until_complete("test-uuid", poll_interval=0.01, timeout=1.0)
            self.assertEqual(status, "FAILED")
            self.assertIsNone(doc)
            self.assertEqual(err, "Image corrupt or unreadable")


class TestCommandHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_start_command(self):
        update = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()

        await start_command(update, context)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("LokalityBot", args[0])
        self.assertEqual(kwargs.get("parse_mode"), ParseMode.HTML)

    async def test_help_command(self):
        update = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()

        await help_command(update, context)
        update.effective_message.reply_text.assert_called_once()
        args, kwargs = update.effective_message.reply_text.call_args
        self.assertIn("Panduan Penggunaan", args[0])

    async def test_status_command(self):
        update = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()

        with patch("bot.handlers.ocr_client.check_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = True
            await status_command(update, context)
            update.effective_message.reply_text.assert_called_once()
            args, _ = update.effective_message.reply_text.call_args
            self.assertIn("ONLINE", args[0])


class TestBotBuilder(unittest.TestCase):
    def test_builder_without_token_raises(self):
        with patch("bot.main.TELEGRAM_BOT_TOKEN", ""):
            with self.assertRaises(ValueError):
                build_bot_app()

    def test_builder_with_token_builds(self):
        with patch("bot.main.TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"):
            app = build_bot_app()
            self.assertIsNotNone(app)


class TestInlineKeyboards(unittest.TestCase):
    def test_confirmation_keyboard(self):
        kb = build_confirmation_keyboard(42)
        self.assertEqual(len(kb.inline_keyboard), 1)
        self.assertEqual(len(kb.inline_keyboard[0]), 2)
        self.assertEqual(kb.inline_keyboard[0][0].text, "✅ Sesuai")
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "tx_confirm:42")
        self.assertEqual(kb.inline_keyboard[0][1].text, "✏️ Belum Sesuai")
        self.assertEqual(kb.inline_keyboard[0][1].callback_data, "tx_edit:42")

    def test_category_keyboard(self):
        kb = build_category_keyboard(42)
        # Check all categories appear in buttons
        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        for cat in CATEGORIES:
            self.assertIn(cat, button_texts)
        self.assertIn("🔙 Batal / Kembali", button_texts)

    def test_subcategory_keyboard(self):
        cat_idx = CATEGORIES.index("Beban Operasional")
        kb = build_subcategory_keyboard(42, cat_idx)
        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        for sub in CATEGORY_HIERARCHY["Beban Operasional"]:
            self.assertIn(sub, button_texts)
        self.assertIn("🔙 Pilih Kategori Lain", button_texts)

    def test_category_keyboard_filtered_by_tx_type(self):
        # EXPENSES should not include 'Penjualan'
        kb_exp = build_category_keyboard(42, tx_type="EXPENSES")
        exp_texts = [btn.text for row in kb_exp.inline_keyboard for btn in row]
        self.assertNotIn("Penjualan", exp_texts)
        self.assertIn("Beban Operasional", exp_texts)
        self.assertIn("Persediaan", exp_texts)

        # INCOMING should not include 'Persediaan' or 'Beban Operasional'
        kb_inc = build_category_keyboard(42, tx_type="INCOMING")
        inc_texts = [btn.text for row in kb_inc.inline_keyboard for btn in row]
        self.assertIn("Penjualan", inc_texts)
        self.assertNotIn("Persediaan", inc_texts)
        self.assertNotIn("Beban Operasional", inc_texts)

    def test_subcategory_keyboard_filtered_by_tx_type(self):
        cat_idx = CATEGORIES.index("Modal dan Prive")
        # EXPENSES for Modal and Prive should only show Prive, not Modal
        kb_exp = build_subcategory_keyboard(42, cat_idx, tx_type="EXPENSES")
        exp_subs = [btn.text for row in kb_exp.inline_keyboard for btn in row]
        self.assertIn("Prive", exp_subs)
        self.assertNotIn("Modal", exp_subs)

        # INCOMING for Modal and Prive should only show Modal, not Prive
        kb_inc = build_subcategory_keyboard(42, cat_idx, tx_type="INCOMING")
        inc_subs = [btn.text for row in kb_inc.inline_keyboard for btn in row]
        self.assertIn("Modal", inc_subs)
        self.assertNotIn("Prive", inc_subs)


class TestCallbackQueryHandler(unittest.IsolatedAsyncioTestCase):
    async def test_handle_confirm(self):
        update = MagicMock()
        query = AsyncMock()
        query.data = "tx_confirm:42"
        query.from_user.id = 12345
        update.callback_query = query
        context = MagicMock()

        with patch("bot.handlers.ocr_client.get_document", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": 42, "amount": 50000, "category": "Persediaan", "sub_category": "Bahan Baku"}
            await handle_callback_query(update, context)
            query.answer.assert_called_once()
            query.edit_message_text.assert_called_once()
            kwargs = query.edit_message_text.call_args.kwargs
            self.assertIn("Terkonfirmasi (Sesuai) [Terkunci]", kwargs["text"])
            self.assertIsNone(kwargs["reply_markup"])

    async def test_handle_edit(self):
        update = MagicMock()
        query = AsyncMock()
        query.data = "tx_edit:42"
        update.callback_query = query
        context = MagicMock()

        await handle_callback_query(update, context)
        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        kwargs = query.edit_message_text.call_args.kwargs
        self.assertIn("Edit Kategori Transaksi", kwargs["text"])
        self.assertIsNotNone(kwargs["reply_markup"])

    async def test_handle_cat(self):
        update = MagicMock()
        query = AsyncMock()
        cat_idx = CATEGORIES.index("Beban Operasional")
        query.data = f"tx_cat:42:{cat_idx}"
        update.callback_query = query
        context = MagicMock()

        await handle_callback_query(update, context)
        query.answer.assert_called_once()
        query.edit_message_text.assert_called_once()
        kwargs = query.edit_message_text.call_args.kwargs
        self.assertIn("Beban Operasional", kwargs["text"])
        self.assertIn("Sub Kategori", kwargs["text"])
        self.assertIsNotNone(kwargs["reply_markup"])

    async def test_handle_sub(self):
        update = MagicMock()
        query = AsyncMock()
        cat_idx = CATEGORIES.index("Beban Operasional")
        sub_idx = CATEGORY_HIERARCHY["Beban Operasional"].index("Biaya-Konsumsi")
        query.data = f"tx_sub:42:{cat_idx}:{sub_idx}"
        update.callback_query = query
        context = MagicMock()

        with patch("bot.handlers.ocr_client.update_document", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = {
                "id": 42,
                "amount": 50000,
                "category": "Beban Operasional",
                "sub_category": "Biaya-Konsumsi",
            }
            await handle_callback_query(update, context)
            mock_update.assert_called_once_with(42, {"category": "Beban Operasional", "sub_category": "Biaya-Konsumsi"})
            query.edit_message_text.assert_called_once()
            kwargs = query.edit_message_text.call_args.kwargs
            self.assertIn("Kategori Diperbarui", kwargs["text"])
            self.assertIn("Biaya-Konsumsi", kwargs["text"])
            self.assertIsNone(kwargs["reply_markup"])

    async def test_handle_back(self):
        update = MagicMock()
        query = AsyncMock()
        query.data = "tx_back:42"
        update.callback_query = query
        context = MagicMock()

        with patch("bot.handlers.ocr_client.get_document", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": 42, "amount": 50000, "category": "Persediaan", "sub_category": "Bahan Baku"}
            await handle_callback_query(update, context)
            query.answer.assert_called_once()
            query.edit_message_text.assert_called_once()
            kwargs = query.edit_message_text.call_args.kwargs
            self.assertIsNotNone(kwargs["reply_markup"])

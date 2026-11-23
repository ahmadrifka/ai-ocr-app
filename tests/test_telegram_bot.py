import io
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from PIL import Image
from telegram.constants import ParseMode

from bot.client import OcrApiClient
from bot.formatters import (
    format_currency,
    format_duplicate_notice,
    format_ocr_failure,
    format_transaction_success,
)
from bot.handlers import (
    _normalize_image_to_jpeg,
    help_command,
    start_command,
    status_command,
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

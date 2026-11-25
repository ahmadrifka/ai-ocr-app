"""Single-instance runtime: embedded OCR worker and Telegram webhook mode."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
from telegram import Update

from app import main
from app.main import app
from bot.client import API_KEY_HEADER, OcrApiClient
from bot.webhook import SECRET_TOKEN_HEADER, WEBHOOK_PATH, TelegramWebhook


BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
SECRET = "webhook-secret"


def telegram_application() -> MagicMock:
    application = MagicMock()
    application.initialize = AsyncMock()
    application.start = AsyncMock()
    application.stop = AsyncMock()
    application.shutdown = AsyncMock()
    application.bot.set_webhook = AsyncMock()
    application.update_queue = asyncio.Queue()
    return application


class EmbeddedWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_runs_worker_and_cancels_it_on_shutdown(self):
        worker_started = asyncio.Event()
        worker_cancelled = asyncio.Event()

        async def fake_worker_loop(_sessions):
            worker_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                worker_cancelled.set()
                raise

        with (
            patch.object(main, "RUN_WORKER_IN_API", True),
            patch.object(main, "worker_loop", fake_worker_loop),
            patch.object(main, "init_db", AsyncMock()),
            patch.object(main, "TELEGRAM_WEBHOOK_ENABLED", False),
        ):
            async with main.lifespan(app):
                await asyncio.wait_for(worker_started.wait(), timeout=1)
                self.assertFalse(worker_cancelled.is_set())

        self.assertTrue(worker_cancelled.is_set())

    async def test_lifespan_skips_worker_by_default(self):
        worker_loop = AsyncMock()

        with (
            patch.object(main, "RUN_WORKER_IN_API", False),
            patch.object(main, "worker_loop", worker_loop),
            patch.object(main, "init_db", AsyncMock()),
            patch.object(main, "TELEGRAM_WEBHOOK_ENABLED", False),
        ):
            async with main.lifespan(app):
                pass

        worker_loop.assert_not_called()


class TelegramWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_registers_webhook_with_secret(self):
        application = telegram_application()
        webhook = TelegramWebhook(application, SECRET)

        await webhook.start("https://ocr.example.com/")

        application.start.assert_awaited_once()
        application.bot.set_webhook.assert_awaited_once()
        kwargs = application.bot.set_webhook.await_args.kwargs
        self.assertEqual(kwargs["url"], f"https://ocr.example.com{WEBHOOK_PATH}")
        self.assertEqual(kwargs["secret_token"], SECRET)

    async def test_start_requires_public_url(self):
        webhook = TelegramWebhook(telegram_application(), SECRET)

        with self.assertRaises(ValueError):
            await webhook.start("")

    async def test_enqueue_parses_update_for_the_application(self):
        with (
            patch("bot.main.TELEGRAM_BOT_TOKEN", BOT_TOKEN),
            patch("bot.webhook.TELEGRAM_WEBHOOK_SECRET", SECRET),
        ):
            webhook = TelegramWebhook.from_config()

        await webhook.enqueue({"update_id": 42})

        queued = webhook._application.update_queue.get_nowait()
        self.assertIsInstance(queued, Update)
        self.assertEqual(queued.update_id, 42)

    def test_secret_is_required(self):
        with self.assertRaises(ValueError):
            TelegramWebhook(telegram_application(), "")


class TelegramWebhookRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        previous = getattr(app.state, "telegram_webhook", None)
        self.addCleanup(setattr, app.state, "telegram_webhook", previous)

    async def post_update(self, secret: str | None):
        headers = {SECRET_TOKEN_HEADER: secret} if secret else {}
        return await self.client.post(WEBHOOK_PATH, json={"update_id": 7}, headers=headers)

    async def test_route_is_hidden_when_webhook_is_disabled(self):
        app.state.telegram_webhook = None

        response = await self.post_update(SECRET)

        self.assertEqual(response.status_code, 404)

    async def test_wrong_or_missing_secret_is_rejected(self):
        application = telegram_application()
        app.state.telegram_webhook = TelegramWebhook(application, SECRET)

        for secret in ("guess", None):
            with self.subTest(secret=secret):
                response = await self.post_update(secret)
                self.assertEqual(response.status_code, 403)
        self.assertTrue(application.update_queue.empty())

    async def test_authentic_update_is_queued(self):
        webhook = MagicMock(spec=TelegramWebhook)
        webhook.is_authentic.return_value = True
        app.state.telegram_webhook = webhook

        response = await self.post_update(SECRET)

        self.assertEqual(response.status_code, 200)
        webhook.is_authentic.assert_called_once_with(SECRET)
        webhook.enqueue.assert_awaited_once_with({"update_id": 7})


class BotApiKeyTests(unittest.TestCase):
    def test_client_sends_api_key_when_configured(self):
        client = OcrApiClient("http://api", api_key="machine-key")

        self.assertEqual(client._client(timeout=5).headers[API_KEY_HEADER], "machine-key")

    def test_client_omits_header_without_api_key(self):
        client = OcrApiClient("http://api")

        self.assertNotIn(API_KEY_HEADER, client._client(timeout=5).headers)


if __name__ == "__main__":
    unittest.main()

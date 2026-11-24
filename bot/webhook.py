"""Run the Telegram bot in webhook mode inside the API process.

Webhook mode lets a sleeping single-instance host (e.g. Render free tier) be woken
by Telegram, which polling mode cannot do.
"""

import hmac
import logging
from typing import Any

from telegram import Update
from telegram.ext import Application

from bot.config import TELEGRAM_WEBHOOK_SECRET
from bot.main import build_bot_app


logger = logging.getLogger(__name__)
WEBHOOK_PATH = "/telegram/webhook"
SECRET_TOKEN_HEADER = "X-Telegram-Bot-Api-Secret-Token"


class TelegramWebhook:
    def __init__(self, application: Application, secret_token: str) -> None:
        if not secret_token:
            raise ValueError("A webhook secret token is required")
        self._application = application
        self._secret_token = secret_token

    @classmethod
    def from_config(cls) -> "TelegramWebhook":
        return cls(build_bot_app(), TELEGRAM_WEBHOOK_SECRET)

    async def start(self, public_base_url: str) -> None:
        """Start processing updates and register the webhook URL with Telegram."""
        if not public_base_url:
            raise ValueError("PUBLIC_BASE_URL is required to register the Telegram webhook")
        await self._application.initialize()
        await self._application.start()
        webhook_url = f"{public_base_url.rstrip('/')}{WEBHOOK_PATH}"
        await self._application.bot.set_webhook(
            url=webhook_url,
            secret_token=self._secret_token,
            allowed_updates=Update.ALL_TYPES,
        )
        logger.info("Telegram webhook registered at %s", webhook_url)

    async def stop(self) -> None:
        # The webhook stays registered so Telegram can wake the service after it sleeps.
        await self._application.stop()
        await self._application.shutdown()

    def is_authentic(self, secret_token: str | None) -> bool:
        return hmac.compare_digest(secret_token or "", self._secret_token)

    async def enqueue(self, payload: dict[str, Any]) -> None:
        """Queue an update so the HTTP request returns before slow OCR handlers finish."""
        update = Update.de_json(payload, self._application.bot)
        await self._application.update_queue.put(update)

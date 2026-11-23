"""Main entrypoint for LokalityBot Telegram daemon."""

import logging
import sys
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from bot.config import ALLOWED_TELEGRAM_USER_IDS, TELEGRAM_BOT_TOKEN
from bot.handlers import (
    handle_document,
    handle_photo,
    handle_text,
    help_command,
    start_command,
    status_command,
    whitelist_guard,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_bot_app():
    """Construct and configure the Telegram application."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set in environment or .env file!")
        raise ValueError("TELEGRAM_BOT_TOKEN is required to run the bot.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Whitelist guard (Silent Drop for unauthorized users)
    if ALLOWED_TELEGRAM_USER_IDS:
        logger.info("Silent drop whitelist active for user IDs: %s", ALLOWED_TELEGRAM_USER_IDS)
        app.add_handler(TypeHandler(Update, whitelist_guard), group=-1)

    # Register commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))

    # Register media & text handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


def main():
    """Run bot polling."""
    logger.info("Initializing LokalityBot...")
    try:
        app = build_bot_app()
        logger.info("LokalityBot starting polling mode...")
        app.run_polling()
    except Exception as exc:
        logger.exception("Fatal error starting bot: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

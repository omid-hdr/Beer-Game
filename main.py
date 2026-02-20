import logging
from telegram.ext import ApplicationBuilder

from config import Config
from infrastructure.repositories import InMemoryGameRepository
from presentation.admin_handlers import get_admin_conversation_handler, get_report_handlers
from presentation.player_handlers import get_player_handlers, get_gameplay_handlers

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting Beer Distribution Game Bot...")

    # 1. Init Repository
    repo = InMemoryGameRepository()

    # 2. Build App using your exact working method
    builder = ApplicationBuilder().token(Config.BOT_TOKEN)

    # if Config.PROXY_URL:
    #     logger.info(f"Routing traffic through proxy: {Config.PROXY_URL}")
    #     builder = builder.proxy_url(Config.PROXY_URL)

    app = builder.build()

    # 3. Register Handlers
    app.add_handler(get_admin_conversation_handler(repo))
    app.add_handler(get_report_handlers(repo))

    for handler in get_player_handlers(repo):
        app.add_handler(handler)

    for handler in get_gameplay_handlers(repo):
        app.add_handler(handler)

    # 4. Start the bot
    logger.info("Bot is polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config import Config
from infrastructure.repositories import InMemoryGameRepository
from presentation.admin_handlers import get_admin_conversation_handler, get_report_handlers
from presentation.player_handlers import get_player_handlers, get_gameplay_handlers
import resources  # Import the new text resources

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Silence noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the welcome message."""
    await update.message.reply_text(resources.START_TEXT, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the help guide."""
    logger.info(f"ℹ️ ACTION: User {update.effective_user.id} requested /help.")
    await update.message.reply_text(resources.HELP_TEXT, parse_mode="Markdown")


def main():
    logger.info("🚀 Starting Beer Distribution Game Bot...")

    # 1. Init Repository
    repo = InMemoryGameRepository()

    # 2. Build App
    builder = ApplicationBuilder().token(Config.BOT_TOKEN)

    app = builder.build()

    # 3. Register Handlers
    app.add_handler(CommandHandler("start", start_command))  # Added /start
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(get_admin_conversation_handler(repo))
    app.add_handler(get_report_handlers(repo))

    for handler in get_player_handlers(repo):
        app.add_handler(handler)

    for handler in get_gameplay_handlers(repo):
        app.add_handler(handler)

    # 4. Start the bot
    logger.info("✅ Bot is polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
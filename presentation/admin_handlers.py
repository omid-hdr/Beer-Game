from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler, MessageHandler, filters
from domain.models import GameSession, GameConfig
from application.interfaces import IGameRepository
import string
import secrets
import logging

# IMPORT THE REPORTING UTILS
from utils.reporting import create_global_cost_bar_chart, create_team_inventory_chart

logger = logging.getLogger(__name__)

# Conversation States
ASK_ROUNDS, ASK_DEMAND = range(2)


def generate_short_id(length: int = 5) -> str:
    """Generates a secure, readable random string (e.g., A1B2C)."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_admin_conversation_handler(repo: IGameRepository) -> ConversationHandler:
    async def start_new_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text(
            "⚙️ *Beer Distribution Game Setup*\n\n"
            "How many rounds (weeks) should this simulation last?",
            parse_mode="Markdown"
        )
        return ASK_ROUNDS

    async def handle_rounds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            rounds = int(update.message.text.strip())
            if rounds <= 0: raise ValueError
            context.user_data['rounds'] = rounds
        except ValueError:
            await update.message.reply_text("Please enter a valid positive integer for the rounds.")
            return ASK_ROUNDS

        await update.message.reply_text(
            "Great. Now, enter the customer demand pattern as a comma-separated list.\n"
            "*(e.g., `4, 4, 8, 8`. If shorter than the total rounds, the last number will be repeated)*",
            parse_mode="Markdown"
        )
        return ASK_DEMAND

    async def handle_demand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            demand_str = update.message.text.strip()
            demand_pattern = [int(x.strip()) for x in demand_str.split(',')]
        except ValueError:
            await update.message.reply_text(
                "Invalid format. Please send a comma-separated list of numbers (e.g., 4, 4, 8, 8).")
            return ASK_DEMAND

        rounds = context.user_data['rounds']
        game_id = generate_short_id()

        # Instantiate the Phase 1 domain model
        new_game = GameSession(
            game_id=game_id,
            total_rounds=rounds,
            demand_pattern=demand_pattern,
            config=GameConfig()  # Using default costs and inventory
        )

        # Save to our infrastructure layer
        await repo.save_game(new_game)

        # Clear temporary state
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ *Game Created Successfully!*\n\n"
            f"🎮 *Game ID:* `{game_id}`\n"
            f"⏳ *Rounds:* {rounds}\n\n"
            f"Share this Game ID with your students. They can join by sending:\n"
            f"`/join {game_id}`",
            parse_mode="Markdown"
        )

        await repo.save_game(new_game)
        logger.info(f"✅ ACTION: Admin {update.effective_user.id} created Game [{game_id}] with {rounds} rounds.")

        return ConversationHandler.END

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data.clear()
        await update.message.reply_text("Game setup cancelled.")
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler("newgame", start_new_game)],
        states={
            ASK_ROUNDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rounds)],
            ASK_DEMAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_demand)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )


# ... (import your reporting utils)
def get_report_handlers(repo: IGameRepository):
    async def generate_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Usage: `/report <Game_ID>`", parse_mode="Markdown")
            return

        game_id = context.args[0].strip().upper()
        game = await repo.get_game(game_id)

        if not game:
            await update.message.reply_text("❌ Game not found.")
            return

        await update.message.reply_text("📊 Generating simulation reports... Please wait.")

        try:
            # 1. Send Team-specific Bullwhip Charts
            for team_code in game.teams.keys():
                inv_buf = create_team_inventory_chart(game, team_code)
                await context.bot.send_photo(
                    chat_id=update.message.chat_id,
                    photo=inv_buf,
                    caption=f"📉 **Inventory Analytics - Team {team_code}**",
                    parse_mode="Markdown"
                )

            # 2. Send Global Leaderboard Chart
            if len(game.teams) > 0:
                global_bar_buf = create_global_cost_bar_chart(game)
                await context.bot.send_photo(
                    chat_id=update.message.chat_id,
                    photo=global_bar_buf,
                    caption=f"🏆 **Global Leaderboard (Total Costs) - Game {game_id}**\n*(Lower is better)*",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Failed to generate reports: {e}")
            await update.message.reply_text(
                "⚠️ An error occurred while generating the charts. Ensure at least one week has been played.")

    return CommandHandler("report", generate_reports)
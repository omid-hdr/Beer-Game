from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from domain.models import GameSession, GameConfig
from application.interfaces import IGameRepository
import string
import secrets
import logging

from utils.reporting import create_global_cost_bar_chart, create_team_inventory_chart

logger = logging.getLogger(__name__)

# استیت‌های جدید برای مکالمه اضافه شدند
ASK_ROUNDS, ASK_DEMAND, ASK_INVENTORY, ASK_PIPELINE = range(4)


def generate_short_id(length: int = 5) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_admin_conversation_handler(repo: IGameRepository) -> ConversationHandler:
    async def start_new_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("⚙️ **تنظیمات بازی جدید**\n\nتعداد راندهای (هفته‌های) بازی چقدر باشد؟",
                                        parse_mode="Markdown")
        return ASK_ROUNDS

    async def handle_rounds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            rounds = int(update.message.text.strip())
            if rounds <= 0: raise ValueError
            context.user_data['rounds'] = rounds
        except ValueError:
            await update.message.reply_text("❌ لطفا یک عدد صحیح و مثبت وارد کنید.")
            return ASK_ROUNDS

        await update.message.reply_text("الگوی تقاضای مشتری را با کاما جدا کنید.\n*(مثال: 4, 4, 8, 8)*",
                                        parse_mode="Markdown")
        return ASK_DEMAND

    async def handle_demand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            demand_pattern = [int(x.strip()) for x in update.message.text.split(',')]
            context.user_data['demand_pattern'] = demand_pattern
        except ValueError:
            await update.message.reply_text("❌ فرمت نامعتبر. لطفا اعداد را با کاما جدا کنید.")
            return ASK_DEMAND

        await update.message.reply_text(
            "📦 **موجودی اولیه (Inventory)** در انبارِ هر نقش در شروع بازی چقدر باشد؟ (مثلا: 12)", parse_mode="Markdown")
        return ASK_INVENTORY

    async def handle_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            context.user_data['starting_inventory'] = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ لطفا یک عدد صحیح وارد کنید.")
            return ASK_INVENTORY

        await update.message.reply_text(
            "🚚 **ظرفیت اولیه کامیون‌های در مسیر (Pipeline)** چقدر باشد؟\n*(یعنی بارهایی که الان در راه هستند. مثلا: 4)*",
            parse_mode="Markdown")
        return ASK_PIPELINE

    async def handle_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            starting_pipeline = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ لطفا یک عدد صحیح وارد کنید.")
            return ASK_PIPELINE

        # حالا همه اطلاعات را داریم، بازی را می‌سازیم
        rounds = context.user_data['rounds']
        demand_pattern = context.user_data['demand_pattern']
        starting_inventory = context.user_data['starting_inventory']
        game_id = generate_short_id()

        config = GameConfig(
            starting_inventory=starting_inventory,
            starting_pipeline=starting_pipeline
        )

        new_game = GameSession(
            game_id=game_id,
            total_rounds=rounds,
            demand_pattern=demand_pattern,
            config=config
        )

        await repo.save_game(new_game)
        logger.info(f"✅ ACTION: Admin {update.effective_user.id} created Game [{game_id}]")
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ **بازی با موفقیت ساخته شد!**\n\n"
            f"🎮 **Game ID:** `{game_id}`\n"
            f"⏳ **راندها:** {rounds}\n"
            f"📦 **موجودی اولیه انبار:** {starting_inventory}\n"
            f"🚚 **بار اولیه در راه:** {starting_pipeline}\n\n"
            f"این Game ID را به دانشجویان بدهید تا با کامند زیر جوین شوند:\n"
            f"`/join {game_id}`",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        context.user_data.clear()
        await update.message.reply_text("ساخت بازی لغو شد.")
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[CommandHandler("newgame", start_new_game)],
        states={
            ASK_ROUNDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rounds)],
            ASK_DEMAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_demand)],
            ASK_INVENTORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_inventory)],
            ASK_PIPELINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pipeline)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )


# ... (بقیه کدهای get_report_handlers دست نخورده باقی بماند)

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
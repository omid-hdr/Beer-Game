from domain.models import GameSession, GameConfig
from application.interfaces import IGameRepository
import string
import secrets
import logging
import random
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

logger = logging.getLogger(__name__)

ASK_ROUNDS, ASK_DEMAND_TYPE, HANDLE_DEMAND_INPUT, ASK_INVENTORY, ASK_PIPELINE = range(5)


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

        # NEW: Ask for Demand Type using a Reply Keyboard
        reply_keyboard = [['STEP', 'RANDOM', 'MANUAL']]
        await update.message.reply_text(
            "نحوه تولید تقاضای مشتری را انتخاب کنید:\n\n"
            "🔹 **STEP:** پرش در یک هفته خاص\n"
            "🔹 **RANDOM:** اعداد تصادفی در یک بازه\n"
            "🔹 **MANUAL:** وارد کردن دستی با کاما",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return ASK_DEMAND_TYPE

    async def handle_demand_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        choice = update.message.text.strip().upper()
        context.user_data['demand_type'] = choice

        if choice == 'STEP':
            await update.message.reply_text(
                "لطفا ۳ عدد را با فاصله وارد کنید (مقدار اولیه، هفته پرش، مقدار پرش):\nمثال: `3 5 2`",
                reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
            return HANDLE_DEMAND_INPUT
        elif choice == 'RANDOM':
            await update.message.reply_text("لطفا ۲ عدد را با فاصله وارد کنید (حداقل، حداکثر):\nمثال: `3 10`",
                                            reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
            return HANDLE_DEMAND_INPUT
        elif choice == 'MANUAL':
            await update.message.reply_text("لطفا مقادیر را با کاما جدا کنید:\nمثال: `4, 4, 8, 8`",
                                            reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
            return HANDLE_DEMAND_INPUT
        else:
            await update.message.reply_text("لطفا یکی از گزینه‌های روی کیبورد را انتخاب کنید.")
            return ASK_DEMAND_TYPE

    async def handle_demand_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        choice = context.user_data.get('demand_type')
        rounds = context.user_data['rounds']
        text = update.message.text.strip()
        demand_pattern = []

        try:
            if choice == 'STEP':
                init_val, jump_week, jump_amt = map(int, text.split())
                for w in range(1, rounds + 1):
                    if w >= jump_week:
                        demand_pattern.append(init_val + jump_amt)
                    else:
                        demand_pattern.append(init_val)
            elif choice == 'RANDOM':
                min_val, max_val = map(int, text.split())
                demand_pattern = [random.randint(min_val, max_val) for _ in range(rounds)]
            elif choice == 'MANUAL':
                demand_pattern = [int(x.strip()) for x in text.split(',')]
        except Exception:
            await update.message.reply_text("❌ فرمت نامعتبر است. لطفا دوباره مطابق مثال وارد کنید.")
            return HANDLE_DEMAND_INPUT

        context.user_data['demand_pattern'] = demand_pattern
        await update.message.reply_text(
            "📦 **موجودی اولیه (Inventory)** در انبارِ هر نقش در شروع بازی چقدر باشد؟ (مثلا: 12)", parse_mode="Markdown")
        return ASK_INVENTORY

    # ... (Keep handle_inventory, handle_pipeline, and cancel EXACTLY as they were before) ...
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
            ASK_DEMAND_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_demand_type)],
            HANDLE_DEMAND_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_demand_input)],
            ASK_INVENTORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_inventory)],
            ASK_PIPELINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pipeline)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )


# Inside presentation/admin_handlers.py
from utils.reporting import create_global_cost_bar_chart, create_team_inventory_chart, create_team_detailed_dashboard


def get_report_handlers(repo: IGameRepository):
    async def generate_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) == 0:
            await update.message.reply_text("راهنما: `/report <Game_ID> [Team_Code]`", parse_mode="Markdown")
            return

        game_id = context.args[0].strip().upper()
        game = await repo.get_game(game_id)

        if not game:
            await update.message.reply_text("❌ بازی پیدا نشد.")
            return

        # 1. GLOBAL REPORT (Only Game ID provided)
        if len(context.args) == 1:
            await update.message.reply_text("📊 در حال تولید گزارشات کلی... لطفا صبر کنید.")

            team_list = "\n".join([f"🔹 `{code}`" for code in game.teams.keys()])
            if not team_list:
                team_list = "هنوز تیمی تشکیل نشده است."

            summary_text = (
                f"📊 **گزارش کلی بازی {game_id}**\n\n"
                f"👥 **تیم‌های شرکت‌کننده:**\n{team_list}\n\n"
                f"🔎 **برای مشاهده جزئیات هر تیم دستور زیر را وارد کنید:**\n"
                f"`/report {game_id} <Team_Code>`"
            )

            # Send Global Chart
            if len(game.teams) > 0:
                global_bar_buf = create_global_cost_bar_chart(game)
                await context.bot.send_photo(
                    chat_id=update.message.chat_id,
                    photo=global_bar_buf,
                    caption=summary_text,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(summary_text, parse_mode="Markdown")

        # 2. TEAM DETAILED REPORT (Game ID + Team Code provided)
        elif len(context.args) >= 2:
            team_code = context.args[1].strip().upper()
            if team_code not in game.teams:
                await update.message.reply_text(f"❌ تیم `{team_code}` در این بازی یافت نشد.", parse_mode="Markdown")
                return

            await update.message.reply_text(f"📈 در حال تولید داشبورد دقیق برای تیم {team_code}...")

            # Send Inventory Overview
            inv_buf = create_team_inventory_chart(game, team_code)
            await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=inv_buf,
                caption=f"📉 **اثر شلاق چرمی (موجودی) - تیم {team_code}**",
                parse_mode="Markdown"
            )

            # Send Detailed Dashboard (Inv vs Backlog vs Orders)
            dash_buf = create_team_detailed_dashboard(game, team_code)
            await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=dash_buf,
                caption=f"📊 **داشبورد تفکیکی نقش‌ها - تیم {team_code}**",
                parse_mode="Markdown"
            )

    return CommandHandler("report", generate_reports)
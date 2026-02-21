import secrets
import string
import logging
import resources
import telegram
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, filters, MessageHandler
from domain.models import TeamState, Role
from application.interfaces import IGameRepository
from presentation.keyboards import get_lobby_keyboard, get_role_selection_keyboard

logger = logging.getLogger(__name__)


def generate_team_code(length: int = 4) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_player_handlers(repo: IGameRepository):
    async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles /join <Game_ID>"""
        if not context.args or len(context.args) != 1:
            await update.message.reply_text("⚠️ Usage: `/join <Game_ID>`", parse_mode="Markdown")
            return

        game_id = context.args[0].strip().upper()
        logger.info(f"🔍 ACTION: User {update.effective_user.id} is attempting to join Game [{game_id}]")

        game = await repo.get_game(game_id)

        if not game:
            logger.warning(f"❌ FAILED: User {update.effective_user.id} tried to join non-existent Game [{game_id}]")
            await update.message.reply_text("❌ Game not found. Please check the ID.")
            return

        await update.message.reply_text(
            f"🍺 *Welcome to the Beer Distribution Game!*\n"
            f"Game ID: `{game_id}`\n\n"
            f"Would you like to create a new team or join an existing one?",
            parse_mode="Markdown",
            reply_markup=get_lobby_keyboard(game_id)
        )

    async def handle_lobby_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the Create Team and Help buttons from the lobby."""
        query = update.callback_query
        await query.answer()

        data = query.data
        if data == "help_join":
            await query.edit_message_text(
                "ℹ️ *To join an existing team:*\n"
                "Ask your team creator for the 4-character Team Code, then send:\n"
                "`/team <Team_Code>`",
                parse_mode="Markdown"
            )
            return

        if data.startswith("create_team:"):
            game_id = data.split(":")[1]
            team_code = generate_team_code()

            game = await repo.get_game(game_id)
            if not game:
                await query.edit_message_text("❌ Game session expired or not found.")
                return

            new_team = TeamState(team_code=team_code)

            for p in new_team.players.values():
                p.inventory = game.config.starting_inventory
                p.shipment_pipeline = [game.config.starting_pipeline, game.config.starting_pipeline]

            game.teams[team_code] = new_team
            await repo.save_game(game)

            keyboard = get_role_selection_keyboard(game_id, team_code, new_team)
            sent_msg = await query.edit_message_text(
                f"✅ *Team Created!*\n\n"
                f"🏷️ *Team Code:* `{team_code}`\n"
                f"*(Share this code with 3 other players so they can run `/team {team_code}`)*\n\n"
                f"Please select your role below:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            if sent_msg:
                await repo.track_lobby_message(team_code, sent_msg.chat_id, sent_msg.message_id)

    async def join_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles /team <Team_Code>"""
        if not context.args or len(context.args) != 1:
            await update.message.reply_text("⚠️ Usage: `/team <Team_Code>`", parse_mode="Markdown")
            return

        team_code = context.args[0].upper()
        game = await repo.get_game_by_team(team_code)

        if not game:
            await update.message.reply_text("❌ Team not found.")
            return

        team_state = game.teams[team_code]
        keyboard = get_role_selection_keyboard(game.game_id, team_code, team_state)

        sent_msg = await update.message.reply_text(
            f"🤝 *Joined Team {team_code}*\n"
            f"Please select an available role:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await repo.track_lobby_message(team_code, sent_msg.chat_id, sent_msg.message_id)

    async def handle_role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the Role selection buttons."""
        query = update.callback_query
        user_id = query.from_user.id

        if query.data == "ignore_click":
            await query.answer("❌ This role is already taken!", show_alert=True)
            return

        _, game_id, team_code, role_value = query.data.split(":")
        role_enum = Role(role_value)

        # NEW: Prevent one user from taking multiple roles in the same team
        game = await repo.get_game(game_id)
        if any(p.user_id == user_id for p in game.teams[team_code].players.values()):
            await query.answer("❌ You already have a role in this team!", show_alert=True)
            return

        # 1. ATOMIC ROLE ASSIGNMENT
        success = await repo.assign_role_atomically(game_id, team_code, role_enum, user_id)

        if not success:
            await query.answer("Too slow! Someone else just took that role.", show_alert=True)
            game = await repo.get_game(game_id)
            new_keyboard = get_role_selection_keyboard(game_id, team_code, game.teams[team_code])
            await query.edit_message_reply_markup(reply_markup=new_keyboard)
            return

        # =================================================================
        # 2. SUCCESS - SAVE USER DATA IMMEDIATELY (Fixing the scope bug)
        # =================================================================
        context.user_data['game_id'] = game_id
        context.user_data['team_code'] = team_code
        context.user_data['role'] = role_enum

        logger.info(f"🎭 ACTION: User {user_id} took role [{role_value}] in Team [{team_code}]")
        await query.answer(f"You are now the {role_value}!")

        # 3. Get fresh state for keyboards
        game = await repo.get_game(game_id)
        team_state = game.teams[team_code]
        new_keyboard = get_role_selection_keyboard(game_id, team_code, team_state)

        # 4. Update the current user's message
        await query.edit_message_text(
            f"✅ *You joined as {role_value}*\n\n"
            f"Team: `{team_code}`\n"
            f"Waiting for other players to join...",
            parse_mode="Markdown",
            reply_markup=new_keyboard
        )

        # 5. LIVE UPDATE everyone else's keyboard in the lobby
        lobby_messages = await repo.get_lobby_messages(team_code)
        for chat_id, msg_id in lobby_messages:
            if chat_id != user_id:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=msg_id,
                        reply_markup=new_keyboard
                    )
                except telegram.error.BadRequest:
                    pass  # Ignore if message hasn't changed or was deleted

        # 6. TRIGGER WEEK 1 FOR EVERYONE
        if all(p.user_id is not None for p in team_state.players.values()):
            logger.info(f"🚀 TEAM FULL: Team [{team_code}] is starting Week 1!")

            for p_role, p_state in team_state.players.items():
                if not p_state.user_id: continue

                start_msg = (
                    f"🚀 **THE SIMULATION HAS STARTED!** 🚀\n\n"
                    f"📅 **WEEK 1**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 **Your Role:** {p_role.value}\n"
                    f"📦 **Current Inventory:** `{p_state.inventory}` units\n"
                    f"⚠️ **Current Backlog:** `{p_state.backlog}` units\n"
                    f"🚚 **Incoming (Next Week):** `{p_state.shipment_pipeline[0]}` units\n"
                    f"🚛 **Incoming (In 2 Weeks):** `{p_state.shipment_pipeline[1]}` units\n"
                    f"💸 **Total Cost Accumulation:** `$0.00`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"✏️ **Please enter your order amount for Week 1 (type a number):**"
                )
                try:
                    await context.bot.send_message(
                        chat_id=p_state.user_id,
                        text=start_msg,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Failed to send start message to {p_state.user_id}: {e}")

    return [
        CommandHandler("join", join_game),
        CommandHandler("team", join_team),
        CallbackQueryHandler(handle_lobby_callbacks, pattern="^(create_team:|help_join)"),
        CallbackQueryHandler(handle_role_selection, pattern="^(take_role:|ignore_click)")
    ]


def get_gameplay_handlers(repo: IGameRepository):
    async def handle_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        logger.info(f"📥 REQUEST: User {user_id} sent text: '{update.message.text}'")

        user_data = context.user_data
        if 'game_id' not in user_data or 'team_code' not in user_data:
            logger.warning(f"⚠️ IGNORED: User {user_id} is not in an active game context.")
            return

        game_id = user_data['game_id']
        team_code = user_data['team_code']
        role = user_data['role']

        game = await repo.get_game(game_id)
        if not game or team_code not in game.teams:
            logger.error(f"❌ ERROR: Game {game_id} or Team {team_code} not found in repository.")
            await update.message.reply_text("❌ Your game session has ended or is invalid.")
            return

        team_state = game.teams[team_code]
        player_state = team_state.players[role]

        if team_state.current_week > game.total_rounds:
            logger.info(f"🛑 REJECTED: User {user_id} ordered, but Game {game_id} is already over.")
            await update.message.reply_text("🏁 The game has already ended! Check with your professor for the results.")
            return

        if player_state.current_order_placed is not None:
            logger.info(
                f"⏳ REJECTED: User {user_id} ({role.value}) already ordered {player_state.current_order_placed} this week.")
            await update.message.reply_text(
                "⏳ You have already placed your order for this week. Waiting for your teammates...")
            return

        try:
            order_amount = int(update.message.text.strip())
            if order_amount < 0: raise ValueError
        except ValueError:
            logger.warning(f"⚠️ INVALID INPUT: User {user_id} sent non-positive integer.")
            await update.message.reply_text("⚠️ Please enter a valid positive number for your order.")
            return

        # --- UPDATE STATE (No explicit handler lock needed, prevents deadlock!) ---
        player_state.current_order_placed = order_amount
        await repo.save_game(game)

        logger.info(
            f"✅ ACCEPTED: User {user_id} ({role.value}) ordered {order_amount} units for Week {team_state.current_week}.")
        await update.message.reply_text(f"📦 Order of **{order_amount}** recorded. Waiting for teammates...",
                                        parse_mode="Markdown")

        # --- SYNCHRONIZATION CHECK ---
        logger.info(f"🔍 CHECKING SYNC FOR TEAM {team_code}...")

        # Build a string showing exactly who is ready and who is missing for the logs
        sync_status = []
        for r, p in team_state.players.items():
            status = str(p.current_order_placed) if p.current_order_placed is not None else "WAITING"
            sync_status.append(f"{r.value}: {status}")

        logger.info(f"📊 TEAM STATUS -> [{', '.join(sync_status)}]")

        if team_state.is_ready_for_next_week():
            logger.info(f"🚀 ALL 4 PLAYERS READY! Advancing Team {team_code} to next week...")
            await process_week_resolution(game, team_code, context, repo)
        else:
            logger.info(f"⏳ Team {team_code} is NOT ready yet.")

    async def process_week_resolution(game, team_code, context: ContextTypes.DEFAULT_TYPE, repo: IGameRepository):
        logger.info(f"⚙️ EXECUTING WEEK RESOLUTION FOR TEAM {team_code}...")
        try:
            team_state = game.teams[team_code]
            demand = game.get_demand_for_week(team_state.current_week)

            team_state.advance_week(customer_demand=demand, config=game.config)
            await repo.save_game(game)

            # 🏁 END OF GAME LOGIC: Send the final report table to each player
            if team_state.current_week > game.total_rounds:
                for role_enum, p_state in team_state.players.items():
                    if not p_state.user_id: continue

                    report_text = resources.get_final_report_header(role_enum.value)
                    report_text += resources.TABLE_HEADER

                    cumulative_cost = 0.0
                    for w in range(game.total_rounds):
                        order_amt = p_state.history_order[w] if w < len(p_state.history_order) else 0
                        inv_amt = p_state.history_inventory[w] if w < len(p_state.history_inventory) else 0
                        bck_amt = p_state.history_backlog[w] if w < len(
                            p_state.history_backlog) else 0  # 👈 Backlog data pulled
                        cost_amt = p_state.history_cost[w] if w < len(p_state.history_cost) else 0
                        cumulative_cost += cost_amt

                        report_text += resources.get_table_row(w, order_amt, inv_amt, bck_amt, cost_amt,
                                                               cumulative_cost)

                    try:
                        await context.bot.send_message(chat_id=p_state.user_id, text=report_text, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Failed to send end report to {p_state.user_id}: {e}")
                return

                # 📢 ONGOING GAME LOGIC
            for role_enum, p_state in team_state.players.items():
                if not p_state.user_id: continue

                truck_1 = p_state.shipment_pipeline[0] if len(p_state.shipment_pipeline) > 0 else 0
                truck_2 = p_state.shipment_pipeline[1] if len(p_state.shipment_pipeline) > 1 else 0

                # Use the Farsi resource generator
                status_msg = resources.get_week_status_msg(
                    week=team_state.current_week,
                    demand=p_state.demand_received,
                    inventory=p_state.inventory,
                    backlog=p_state.backlog,
                    truck1=truck_1,
                    truck2=truck_2,
                    total_cost=p_state.total_cost
                )

                await context.bot.send_message(chat_id=p_state.user_id, text=status_msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"❌ CRITICAL ERROR in process_week_resolution: {e}", exc_info=True)
            await broadcast_to_team(team_state, context, "⚠️ خطایی در سرور رخ داد. لطفا با ادمین تماس بگیرید.")

    async def broadcast_to_team(team_state, context, message: str):
        for role, player in team_state.players.items():
            if player.user_id:
                try:
                    await context.bot.send_message(chat_id=player.user_id, text=message, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"❌ Failed to send message to user {player.user_id} ({role.value}): {e}")

    return [MessageHandler(filters.Regex(r'^\d+$'), handle_order_input)]
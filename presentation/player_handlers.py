import secrets
import string
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, filters, MessageHandler
from domain.models import TeamState, Role
from application.interfaces import IGameRepository
from presentation.keyboards import get_lobby_keyboard, get_role_selection_keyboard
import logging
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
        await query.answer()  # Always answer callbacks to stop the loading spinner

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

            # Create new team and attach to game
            new_team = TeamState(team_code=team_code)
            game.teams[team_code] = new_team
            await repo.save_game(game)  # Save state

            keyboard = get_role_selection_keyboard(game_id, team_code, new_team)
            await query.edit_message_text(
                f"✅ *Team Created!*\n\n"
                f"🏷️ *Team Code:* `{team_code}`\n"
                f"*(Share this code with 3 other players so they can run `/team {team_code}`)*\n\n"
                f"Please select your role below:",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

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

        await update.message.reply_text(
            f"🤝 *Joined Team {team_code}*\n"
            f"Please select an available role:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    async def handle_role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the Role selection buttons."""
        query = update.callback_query
        user_id = query.from_user.id

        if query.data == "ignore_click":
            await query.answer("❌ This role is already taken!", show_alert=True)
            return

        # Parse callback data: "take_role:GAMEID:TEAMCODE:RoleName"
        _, game_id, team_code, role_value = query.data.split(":")
        role_enum = Role(role_value)

        # ATOMIC ROLE ASSIGNMENT
        success = await repo.assign_role_atomically(game_id, team_code, role_enum, user_id)

        if not success:
            # Someone else clicked it milliseconds before this user
            await query.answer("Too slow! Someone else just took that role.", show_alert=True)
            # Re-fetch state and refresh keyboard to show it's taken
            game = await repo.get_game(game_id)
            new_keyboard = get_role_selection_keyboard(game_id, team_code, game.teams[team_code])
            await query.edit_message_reply_markup(reply_markup=new_keyboard)
            return

        # Successfully assigned!
        await query.answer(f"You are now the {role_value}!")

        # Refresh the UI for everyone
        game = await repo.get_game(game_id)
        team_state = game.teams[team_code]
        new_keyboard = get_role_selection_keyboard(game_id, team_code, team_state)

        await query.edit_message_text(
            f"✅ *You joined as {role_value}*\n\n"
            f"Team: `{team_code}`\n"
            f"Waiting for other players to join...",
            parse_mode="Markdown",
            reply_markup=new_keyboard
        )

        # Check if team is full and ready to start
        if all(p.user_id is not None for p in team_state.players.values()):
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🎉 *All roles filled! The simulation is starting...*\nGet ready for Week 1!",
                parse_mode="Markdown"
            )
            # We will trigger the first week's prompt in Phase 4 from here.
            # Add this inside handle_role_selection upon success:
            context.user_data['game_id'] = game_id
            context.user_data['team_code'] = team_code
            context.user_data['role'] = role_enum
    return [
        CommandHandler("join", join_game),
        CommandHandler("team", join_team),
        CallbackQueryHandler(handle_lobby_callbacks, pattern="^(create_team:|help_join)"),
        CallbackQueryHandler(handle_role_selection, pattern="^(take_role:|ignore_click)")
    ]


def get_gameplay_handlers(repo: IGameRepository):
    async def handle_order_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Catches raw numbers sent by users and treats them as orders."""

        # 1. Verify user is in an active game
        user_data = context.user_data
        if 'game_id' not in user_data or 'team_code' not in user_data:
            return  # Ignore random numbers from users not in a game

        game_id = user_data['game_id']
        team_code = user_data['team_code']
        role = user_data['role']

        game = await repo.get_game(game_id)
        if not game or team_code not in game.teams:
            await update.message.reply_text("❌ Your game session has ended or is invalid.")
            return

        team_state = game.teams[team_code]
        player_state = team_state.players[role]

        # 2. Check if the game is already finished
        if team_state.current_week > game.total_rounds:
            await update.message.reply_text("🏁 The game has already ended! Check with your professor for the results.")
            return

        # 3. Check if user already ordered this week
        if player_state.current_order_placed is not None:
            await update.message.reply_text(
                "⏳ You have already placed your order for this week. Waiting for your teammates...")
            return

        # 4. Process the order
        try:
            order_amount = int(update.message.text.strip())
            if order_amount < 0: raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid positive number for your order.")
            return

        # Lock the repository to update state safely
        async with repo._lock:  # Using the lock from our InMemory Repo
            player_state.current_order_placed = order_amount
            await repo.save_game(game)

        await update.message.reply_text(
            f"📦 Order of **{order_amount}** recorded for Week {team_state.current_week}. Waiting for teammates...",
            parse_mode="Markdown")

        # 5. Check Synchronization Barrier: Are all 4 orders in?
        if team_state.is_ready_for_next_week():
            await process_week_resolution(game, team_code, context, repo)

    async def process_week_resolution(game, team_code, context: ContextTypes.DEFAULT_TYPE, repo: IGameRepository):
        """Advances the game engine and notifies all players."""
        team_state = game.teams[team_code]

        # Get customer demand for this week
        demand = game.get_demand_for_week(team_state.current_week)

        # Advance the core simulation logic (Phase 1)
        async with repo._lock:
            team_state.advance_week(customer_demand=demand, config=game.config)
            await repo.save_game(game)

        # Check if game just ended
        if team_state.current_week > game.total_rounds:
            await broadcast_to_team(
                team_state, context,
                "🏁 **GAME OVER!** 🏁\nAll rounds completed. Your professor can now generate the final reports."
            )
            return

        # If game continues, broadcast the new week's status to each player
        for role_enum, p_state in team_state.players.items():
            if not p_state.user_id: continue  # Failsafe

            # Formulate the status message
            status_msg = (
                f"📅 **WEEK {team_state.current_week}**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📥 **Incoming Delivery:** You just received items.\n"
                f"📤 **Demand Received:** `{p_state.demand_received}` units\n"
                f"📦 **Current Inventory:** `{p_state.inventory}` units\n"
                f"⚠️ **Current Backlog:** `{p_state.backlog}` units\n"
                f"💸 **Total Cost Accumulation:** `${p_state.total_cost:.2f}`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Please enter your order amount for this week (type a number):"
            )

            await context.bot.send_message(
                chat_id=p_state.user_id,
                text=status_msg,
                parse_mode="Markdown"
            )

    async def broadcast_to_team(team_state, context, message: str):
        """Helper to send a message to all 4 members of a team."""
        for player in team_state.players.values():
            if player.user_id:
                try:
                    await context.bot.send_message(chat_id=player.user_id, text=message, parse_mode="Markdown")
                except Exception as e:
                    print(f"Failed to send message to user {player.user_id}: {e}")

    # The filter ensures we only trigger this handler if the message is strictly digits
    return [MessageHandler(filters.Regex(r'^\d+$'), handle_order_input)]
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from domain.models import TeamState, Role


def get_lobby_keyboard(game_id: str) -> InlineKeyboardMarkup:
    """Provides the initial options after a player joins a game."""
    keyboard = [
        [InlineKeyboardButton("➕ Create New Team", callback_data=f"create_team:{game_id}")],
        # Joining an existing team is done via command as per PRD: /team <Team_Code>
        [InlineKeyboardButton("ℹ️ How to join an existing team?", callback_data="help_join")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_role_selection_keyboard(game_id: str, team_code: str, team_state: TeamState) -> InlineKeyboardMarkup:
    """Dynamically generates the 4 role buttons based on availability."""
    keyboard = []

    for role in Role:
        player = team_state.players[role]
        if player.user_id is None:
            # Role is available
            text = f"✅ {role.value}"
            callback_data = f"take_role:{game_id}:{team_code}:{role.value}"
        else:
            # Role is taken
            text = f"❌ {role.value} (Taken)"
            callback_data = "ignore_click"  # Dead button

        keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])

    return InlineKeyboardMarkup(keyboard)


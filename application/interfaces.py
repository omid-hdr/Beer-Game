from abc import ABC, abstractmethod
from typing import Optional
from domain.models import GameSession, Role


class IGameRepository(ABC):
    @abstractmethod
    async def save_game(self, game: GameSession) -> None:
        """Saves or updates a GameSession."""
        pass

    @abstractmethod
    async def get_game(self, game_id: str) -> Optional[GameSession]:
        """Retrieves a GameSession by its 5-character ID."""
        pass

    @abstractmethod
    async def get_game_by_team(self, team_code: str) -> Optional[GameSession]:
        """Helper to find which game a specific team belongs to."""
        pass

    @abstractmethod
    async def assign_role_atomically(self, game_id: str, team_code: str, role: Role, user_id: int) -> bool:
        """Attempts to assign a role. Returns True if successful, False if already taken."""
        pass

    @abstractmethod
    async def track_lobby_message(self, team_code: str, chat_id: int, message_id: int) -> None:
        """Saves a message ID so it can be updated live when roles are taken."""
        pass

    @abstractmethod
    async def get_lobby_messages(self, team_code: str) -> list[tuple[int, int]]:
        """Returns a list of (chat_id, message_id) for a team's lobby."""
        pass
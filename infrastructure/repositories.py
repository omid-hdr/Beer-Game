import asyncio
from typing import Dict, Optional
from application.interfaces import IGameRepository
from domain.models import GameSession, Role


class InMemoryGameRepository(IGameRepository):
    def __init__(self):
        self._games: Dict[str, GameSession] = {}
        self._lock = asyncio.Lock()
        self._lobby_trackers: Dict[str, list[tuple[int, int]]] = {}  # team_code -> [(chat_id, message_id)]

    async def track_lobby_message(self, team_code: str, chat_id: int, message_id: int) -> None:
        async with self._lock:
            if team_code not in self._lobby_trackers:
                self._lobby_trackers[team_code] = []
            self._lobby_trackers[team_code].append((chat_id, message_id))

    async def get_lobby_messages(self, team_code: str) -> list[tuple[int, int]]:
        async with self._lock:
            return self._lobby_trackers.get(team_code, []).copy()

    async def save_game(self, game: GameSession) -> None:
        async with self._lock:
            self._games[game.game_id] = game

    async def get_game(self, game_id: str) -> Optional[GameSession]:
        async with self._lock:
            return self._games.get(game_id)

    async def get_game_by_team(self, team_code: str) -> Optional[GameSession]:
        async with self._lock:
            for game in self._games.values():
                if team_code in game.teams:
                    return game
        return None

    async def assign_role_atomically(self, game_id: str, team_code: str, role: Role, user_id: int) -> bool:
        async with self._lock:  # Crucial for concurrency
            game = self._games.get(game_id)
            if not game or team_code not in game.teams:
                return False

            player_state = game.teams[team_code].players[role]
            if player_state.user_id is not None:
                return False  # Race condition lost: someone else got it first

            player_state.user_id = user_id
            return True


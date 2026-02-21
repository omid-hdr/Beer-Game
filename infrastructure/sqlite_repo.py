import aiosqlite
import pickle
import asyncio
from typing import Optional
from application.interfaces import IGameRepository
from domain.models import GameSession, Role
import logging

logger = logging.getLogger(__name__)


class SQLiteGameRepository(IGameRepository):
    def __init__(self, db_path: str = "beer_game.db"):
        self.db_path = db_path
        self._lock = asyncio.Lock()  # Keeps our atomic operations safe

    async def initialize(self):
        """Creates the tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Table for Game Sessions
            await db.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    data BLOB
                )
            ''')
            # Table for Lobby Tracking
            await db.execute('''
                CREATE TABLE IF NOT EXISTS lobbies (
                    team_code TEXT,
                    chat_id INTEGER,
                    message_id INTEGER
                )
            ''')
            await db.commit()
            logger.info("📦 SQLite Database initialized.")

    async def save_game(self, game: GameSession) -> None:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                pickled_data = pickle.dumps(game)
                await db.execute(
                    'INSERT OR REPLACE INTO games (game_id, data) VALUES (?, ?)',
                    (game.game_id, pickled_data)
                )
                await db.commit()

    async def get_game(self, game_id: str) -> Optional[GameSession]:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('SELECT data FROM games WHERE game_id = ?', (game_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return pickle.loads(row[0])
        return None

    async def get_game_by_team(self, team_code: str) -> Optional[GameSession]:
        # We deserialize all games to find the team. For a massive bot, this is slow,
        # but for a classroom simulation, it is perfectly fast and fine.
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('SELECT data FROM games') as cursor:
                    async for row in cursor:
                        game: GameSession = pickle.loads(row[0])
                        if team_code in game.teams:
                            return game
        return None

    async def assign_role_atomically(self, game_id: str, team_code: str, role: Role, user_id: int) -> bool:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('SELECT data FROM games WHERE game_id = ?', (game_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row: return False

                    game: GameSession = pickle.loads(row[0])

                    if team_code not in game.teams: return False
                    player_state = game.teams[team_code].players[role]

                    if player_state.user_id is not None:
                        return False  # Role is already taken

                    player_state.user_id = user_id

                    # Save back to DB
                    pickled_data = pickle.dumps(game)
                    await db.execute('UPDATE games SET data = ? WHERE game_id = ?', (pickled_data, game_id))
                    await db.commit()
                    return True

    async def track_lobby_message(self, team_code: str, chat_id: int, message_id: int) -> None:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    'INSERT INTO lobbies (team_code, chat_id, message_id) VALUES (?, ?, ?)',
                    (team_code, chat_id, message_id)
                )
                await db.commit()

    async def get_lobby_messages(self, team_code: str) -> list[tuple[int, int]]:
        messages = []
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute('SELECT chat_id, message_id FROM lobbies WHERE team_code = ?',
                                      (team_code,)) as cursor:
                    async for row in cursor:
                        messages.append((row[0], row[1]))
        return messages
"""
Database Layer - database/database.py
Async SQLite database manager using aiosqlite.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    """
    Async SQLite database manager.
    Handles all persistent storage for the bot.
    """

    def __init__(self, db_path: str = "guardian.db") -> None:
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open the database connection and initialize schema."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()
        logger.info(f"Database connected: {self.db_path}")

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            logger.info("Database connection closed.")

    async def _create_tables(self) -> None:
        """Create all required tables if they don't exist."""
        statements = [
            # Guild settings
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id        INTEGER PRIMARY KEY,
                log_channel_id  INTEGER,
                mod_role_id     INTEGER,
                mute_role_id    INTEGER,
                antinuke_enabled INTEGER DEFAULT 1,
                spam_enabled    INTEGER DEFAULT 1,
                prefix          TEXT DEFAULT '!',
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            )
            """,
            # Whitelisted users per guild
            """
            CREATE TABLE IF NOT EXISTS whitelist (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                added_by    INTEGER NOT NULL,
                added_at    TEXT DEFAULT (datetime('now')),
                UNIQUE(guild_id, user_id)
            )
            """,
            # Moderation actions log
            """
            CREATE TABLE IF NOT EXISTS mod_actions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                action      TEXT NOT NULL,
                reason      TEXT,
                duration    INTEGER,
                created_at  TEXT DEFAULT (datetime('now'))
            )
            """,
            # Warnings
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason      TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
            """,
            # Anti-nuke settings per guild
            """
            CREATE TABLE IF NOT EXISTS antinuke_settings (
                guild_id                INTEGER PRIMARY KEY,
                channel_delete_limit    INTEGER DEFAULT 3,
                channel_delete_window   INTEGER DEFAULT 10,
                channel_create_limit    INTEGER DEFAULT 5,
                channel_create_window   INTEGER DEFAULT 10,
                role_delete_limit       INTEGER DEFAULT 3,
                role_delete_window      INTEGER DEFAULT 10,
                role_create_limit       INTEGER DEFAULT 5,
                role_create_window      INTEGER DEFAULT 10,
                ban_limit               INTEGER DEFAULT 5,
                ban_window              INTEGER DEFAULT 10,
                kick_limit              INTEGER DEFAULT 5,
                kick_window             INTEGER DEFAULT 10,
                webhook_create_limit    INTEGER DEFAULT 3,
                webhook_create_window   INTEGER DEFAULT 10
            )
            """,
            # Spam thresholds per guild
            """
            CREATE TABLE IF NOT EXISTS spam_settings (
                guild_id                INTEGER PRIMARY KEY,
                warn_message_count      INTEGER DEFAULT 5,
                warn_message_window     INTEGER DEFAULT 5,
                mute_message_count      INTEGER DEFAULT 10,
                mute_message_window     INTEGER DEFAULT 5,
                kick_message_count      INTEGER DEFAULT 20,
                kick_message_window     INTEGER DEFAULT 5,
                mute_duration           INTEGER DEFAULT 300
            )
            """,
        ]

        async with self._conn.cursor() as cursor:
            for stmt in statements:
                await cursor.execute(stmt)
        await self._conn.commit()
        logger.debug("Database schema initialized.")

    # ─────────────────────────────────────────────
    # Generic helpers
    # ─────────────────────────────────────────────

    async def fetchone(
        self, query: str, params: Tuple = ()
    ) -> Optional[aiosqlite.Row]:
        async with self._conn.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(
        self, query: str, params: Tuple = ()
    ) -> List[aiosqlite.Row]:
        async with self._conn.execute(query, params) as cursor:
            return await cursor.fetchall()

    async def execute(self, query: str, params: Tuple = ()) -> int:
        """Execute a write query and return lastrowid."""
        async with self._conn.execute(query, params) as cursor:
            await self._conn.commit()
            return cursor.lastrowid

    # ─────────────────────────────────────────────
    # Guild Settings
    # ─────────────────────────────────────────────

    async def get_guild_settings(self, guild_id: int) -> Optional[Dict]:
        row = await self.fetchone(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        return dict(row) if row else None

    async def ensure_guild(self, guild_id: int) -> Dict:
        """Get or create guild settings row."""
        row = await self.get_guild_settings(guild_id)
        if row is None:
            await self.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            row = await self.get_guild_settings(guild_id)
        return dict(row)

    async def set_log_channel(self, guild_id: int, channel_id: int) -> None:
        await self.ensure_guild(guild_id)
        await self.execute(
            "UPDATE guild_settings SET log_channel_id = ?, updated_at = datetime('now') WHERE guild_id = ?",
            (channel_id, guild_id),
        )

    async def get_log_channel(self, guild_id: int) -> Optional[int]:
        row = await self.fetchone(
            "SELECT log_channel_id FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        return row["log_channel_id"] if row else None

    async def set_mute_role(self, guild_id: int, role_id: int) -> None:
        await self.ensure_guild(guild_id)
        await self.execute(
            "UPDATE guild_settings SET mute_role_id = ? WHERE guild_id = ?",
            (role_id, guild_id),
        )

    async def get_mute_role(self, guild_id: int) -> Optional[int]:
        row = await self.fetchone(
            "SELECT mute_role_id FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        return row["mute_role_id"] if row else None

    # ─────────────────────────────────────────────
    # Whitelist
    # ─────────────────────────────────────────────

    async def add_whitelist(
        self, guild_id: int, user_id: int, added_by: int
    ) -> bool:
        """Add user to whitelist. Returns True if added, False if already exists."""
        try:
            await self.execute(
                "INSERT INTO whitelist (guild_id, user_id, added_by) VALUES (?, ?, ?)",
                (guild_id, user_id, added_by),
            )
            return True
        except Exception:
            return False

    async def remove_whitelist(self, guild_id: int, user_id: int) -> bool:
        """Remove user from whitelist. Returns True if removed."""
        async with self._conn.execute(
            "DELETE FROM whitelist WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            await self._conn.commit()
            return cursor.rowcount > 0

    async def is_whitelisted(self, guild_id: int, user_id: int) -> bool:
        row = await self.fetchone(
            "SELECT 1 FROM whitelist WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return row is not None

    async def get_whitelist(self, guild_id: int) -> List[Dict]:
        rows = await self.fetchall(
            "SELECT * FROM whitelist WHERE guild_id = ? ORDER BY added_at DESC",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────
    # Moderation Actions
    # ─────────────────────────────────────────────

    async def log_mod_action(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action: str,
        reason: Optional[str] = None,
        duration: Optional[int] = None,
    ) -> int:
        return await self.execute(
            """INSERT INTO mod_actions
               (guild_id, user_id, moderator_id, action, reason, duration)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, moderator_id, action, reason, duration),
        )

    async def get_user_history(
        self, guild_id: int, user_id: int, limit: int = 10
    ) -> List[Dict]:
        rows = await self.fetchall(
            """SELECT * FROM mod_actions
               WHERE guild_id = ? AND user_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (guild_id, user_id, limit),
        )
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────
    # Warnings
    # ─────────────────────────────────────────────

    async def add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: Optional[str] = None,
    ) -> int:
        return await self.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason),
        )

    async def get_warnings(self, guild_id: int, user_id: int) -> List[Dict]:
        rows = await self.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (guild_id, user_id),
        )
        return [dict(r) for r in rows]

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        async with self._conn.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cursor:
            await self._conn.commit()
            return cursor.rowcount

    # ─────────────────────────────────────────────
    # Anti-Nuke Settings
    # ─────────────────────────────────────────────

    async def get_antinuke_settings(self, guild_id: int) -> Dict:
        row = await self.fetchone(
            "SELECT * FROM antinuke_settings WHERE guild_id = ?", (guild_id,)
        )
        if row is None:
            await self.execute(
                "INSERT OR IGNORE INTO antinuke_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            row = await self.fetchone(
                "SELECT * FROM antinuke_settings WHERE guild_id = ?", (guild_id,)
            )
        return dict(row)

    # ─────────────────────────────────────────────
    # Spam Settings
    # ─────────────────────────────────────────────

    async def get_spam_settings(self, guild_id: int) -> Dict:
        row = await self.fetchone(
            "SELECT * FROM spam_settings WHERE guild_id = ?", (guild_id,)
        )
        if row is None:
            await self.execute(
                "INSERT OR IGNORE INTO spam_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            row = await self.fetchone(
                "SELECT * FROM spam_settings WHERE guild_id = ?", (guild_id,)
            )
        return dict(row)

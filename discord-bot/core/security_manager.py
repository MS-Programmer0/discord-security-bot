"""
Security Manager - core/security_manager.py
Central coordinator for all security checks.
Bridges anti-nuke, whitelist, and permission systems.
"""

import logging
from typing import Optional

import discord

from core.rate_limiter import rate_limiter
from config import config

logger = logging.getLogger(__name__)


class SecurityManager:
    """
    Coordinates security checks across the bot.
    Used by anti-nuke cogs and event listeners.
    """

    def __init__(self, bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.rl = rate_limiter

    # ─────────────────────────────────────────────
    # Whitelist Checks
    # ─────────────────────────────────────────────

    async def is_whitelisted(self, guild_id: int, user_id: int) -> bool:
        """Check if user is whitelisted in the guild."""
        return await self.db.is_whitelisted(guild_id, user_id)

    async def is_exempt(
        self,
        guild: discord.Guild,
        user_id: int,
    ) -> bool:
        """
        Check if user is exempt from anti-nuke checks.
        Exempt = guild owner OR whitelisted.
        """
        if user_id == guild.owner_id:
            return True
        return await self.is_whitelisted(guild.id, user_id)

    # ─────────────────────────────────────────────
    # Anti-Nuke Action Checks
    # ─────────────────────────────────────────────

    async def check_nuke_action(
        self,
        guild: discord.Guild,
        user_id: int,
        action: str,
        limit: int,
        window: int,
    ) -> bool:
        """
        Check if an action triggers nuke detection.

        Returns True if action is a threat and should be blocked.
        """
        # Get antinuke enabled setting
        settings = await self.db.get_guild_settings(guild.id)
        if settings and not settings.get("antinuke_enabled", 1):
            return False  # Anti-nuke disabled

        # Exempt users bypass anti-nuke
        if await self.is_exempt(guild, user_id):
            return False

        exceeded, count = self.rl.check(guild.id, user_id, action, limit, window)
        if exceeded:
            logger.warning(
                f"[ANTI-NUKE] Threat detected in {guild.name}: user {user_id} "
                f"performed {count} '{action}' actions in {window}s (limit={limit})"
            )
        return exceeded

    # ─────────────────────────────────────────────
    # Countermeasures
    # ─────────────────────────────────────────────

    async def punish_attacker(
        self,
        guild: discord.Guild,
        attacker_id: int,
        reason: str,
    ) -> bool:
        """
        Immediately ban the attacker from the guild.
        Returns True if ban succeeded.
        """
        try:
            member = guild.get_member(attacker_id)
            if member is None:
                # Try to ban by ID even if not cached
                await guild.ban(
                    discord.Object(id=attacker_id),
                    reason=f"[ANTI-NUKE] {reason}",
                    delete_message_days=0,
                )
            else:
                await member.ban(
                    reason=f"[ANTI-NUKE] {reason}",
                    delete_message_days=0,
                )

            # Clear rate limit state
            self.rl.reset_user(guild.id, attacker_id)

            logger.info(
                f"[ANTI-NUKE] Banned attacker {attacker_id} from {guild.name}: {reason}"
            )
            return True
        except discord.Forbidden:
            logger.error(
                f"[ANTI-NUKE] Failed to ban {attacker_id} from {guild.name}: Forbidden"
            )
            return False
        except Exception as e:
            logger.error(f"[ANTI-NUKE] Error banning {attacker_id}: {e}")
            return False

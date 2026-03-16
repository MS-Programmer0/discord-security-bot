"""
Audit Monitor - security/audit_monitor.py
Continuously monitors the audit log for suspicious patterns.
Acts as a secondary detection layer in addition to event listeners.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set

import discord
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


class AuditMonitor(commands.Cog, name="AuditMonitor"):
    """
    Periodic audit log scanner.
    Catches edge cases that event listeners might miss due to caching or rate limits.
    Runs every 15 seconds per guild.
    """

    def __init__(self, bot) -> None:
        self.bot = bot
        # Track already-processed audit log entry IDs to avoid duplicate actions
        self._processed_ids: Dict[int, Set[int]] = {}  # {guild_id: {entry_id}}
        self.audit_scan.start()

    def cog_unload(self) -> None:
        self.audit_scan.cancel()

    @tasks.loop(seconds=15)
    async def audit_scan(self) -> None:
        """Scan audit logs for all guilds periodically."""
        for guild in self.bot.guilds:
            try:
                await self._scan_guild(guild)
            except Exception as e:
                logger.debug(f"Audit scan error for {guild.id}: {e}")

    @audit_scan.before_loop
    async def before_audit_scan(self) -> None:
        await self.bot.wait_until_ready()

    async def _scan_guild(self, guild: discord.Guild) -> None:
        """Scan a single guild's recent audit log entries."""
        if guild.id not in self._processed_ids:
            self._processed_ids[guild.id] = set()

        processed = self._processed_ids[guild.id]
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=30)

        suspicious_actions = [
            discord.AuditLogAction.channel_delete,
            discord.AuditLogAction.role_delete,
            discord.AuditLogAction.ban,
            discord.AuditLogAction.webhook_create,
            discord.AuditLogAction.guild_update,
        ]

        for action in suspicious_actions:
            try:
                async for entry in guild.audit_logs(action=action, limit=10):
                    # Skip old entries
                    if entry.created_at < cutoff:
                        break
                    # Skip already processed entries
                    if entry.id in processed:
                        continue

                    processed.add(entry.id)
                    await self._evaluate_entry(guild, entry)

                    # Keep set size bounded
                    if len(processed) > 1000:
                        oldest = sorted(processed)[:500]
                        processed.difference_update(oldest)

            except discord.Forbidden:
                # Bot lacks audit log access
                break
            except discord.HTTPException:
                pass

    async def _evaluate_entry(
        self, guild: discord.Guild, entry: discord.AuditLogEntry
    ) -> None:
        """
        Evaluate a single audit log entry for suspicious patterns.
        This is a secondary check — primary detection is via event listeners.
        """
        if entry.user is None:
            return

        actor_id = entry.user.id

        # Skip bots (including our own bot)
        if entry.user.bot:
            return

        # Check if actor is exempt
        security = self.bot.get_cog("AntiNuke")
        if security and hasattr(security, "security"):
            if await security.security.is_exempt(guild, actor_id):
                return

        # Log suspicious entries for audit trail
        action_name = str(entry.action).replace("AuditLogAction.", "")
        logger.debug(
            f"[AUDIT-SCAN] {guild.name}: {entry.user} performed {action_name}"
        )


async def setup(bot) -> None:
    await bot.add_cog(AuditMonitor(bot))

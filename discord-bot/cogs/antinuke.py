"""
Anti-Nuke Cog - cogs/antinuke.py
Real-time protection against mass destruction attacks using audit log monitoring.
Detects: mass bans, kicks, channel/role deletion/creation, webhook abuse, permission escalation.
"""

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

from config import config
from core.security_manager import SecurityManager
from utils.helpers import get_audit_user
from utils.embeds import antinuke_alert_embed

logger = logging.getLogger(__name__)


class AntiNuke(commands.Cog, name="AntiNuke"):
    """
    Advanced anti-nuke protection cog.
    Monitors guild events and auto-bans attackers who exceed thresholds.
    """

    def __init__(self, bot) -> None:
        self.bot = bot
        self.security: SecurityManager = SecurityManager(bot)
        self._nuke_cfg = config.antinuke  # Default thresholds

    def _get_logging_cog(self):
        return self.bot.get_cog("Logging")

    async def _handle_nuke_event(
        self,
        guild: discord.Guild,
        actor_id: Optional[int],
        action_name: str,
        action_key: str,
        limit: int,
        window: int,
        details: str,
    ) -> None:
        """
        Shared nuke event handler.
        1. Check if actor is exempt (owner/whitelist).
        2. Check rate limit.
        3. If exceeded: ban attacker + alert mods.
        """
        if actor_id is None:
            return  # Can't act without knowing who did it

        # Check if exempt (owner or whitelisted user)
        if await self.security.is_exempt(guild, actor_id):
            return

        # Use security manager's sliding-window check
        exceeded = await self.security.check_nuke_action(
            guild, actor_id, action_key, limit, window
        )

        if exceeded:
            count = self.security.rl.get_count(guild.id, actor_id, action_key, window)

            # Immediately ban the attacker
            success = await self.security.punish_attacker(
                guild, actor_id, f"Anti-nuke: {action_name}"
            )

            # Send alert embed to log channel
            actor = guild.get_member(actor_id)
            alert_embed = antinuke_alert_embed(
                action=action_name,
                attacker=actor,
                attacker_id=actor_id,
                guild=guild,
                details=details,
                count=count,
            )

            log_cog = self._get_logging_cog()
            if log_cog:
                await log_cog.send_log(guild.id, alert_embed)
                await log_cog.log_antinuke(
                    guild, action_name, actor_id, details, count
                )

            # Also log to database
            await self.bot.db.log_mod_action(
                guild.id,
                actor_id,
                self.bot.user.id,
                f"antinuke_ban",
                f"Anti-nuke triggered: {action_name} ({count} events in {window}s)",
            )

    # ─────────────────────────────────────────────
    # Mass Channel Deletion
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        guild = channel.guild
        cfg = self._nuke_cfg

        actor_id = await get_audit_user(
            guild, discord.AuditLogAction.channel_delete
        )
        await self._handle_nuke_event(
            guild=guild,
            actor_id=actor_id,
            action_name="Mass Channel Deletion",
            action_key="channel_delete",
            limit=cfg.channel_delete_limit,
            window=cfg.channel_delete_window,
            details=f"Deleted channel: **{channel.name}** (`{channel.id}`)",
        )

    # ─────────────────────────────────────────────
    # Mass Channel Creation
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        guild = channel.guild
        cfg = self._nuke_cfg

        actor_id = await get_audit_user(
            guild, discord.AuditLogAction.channel_create
        )
        await self._handle_nuke_event(
            guild=guild,
            actor_id=actor_id,
            action_name="Mass Channel Creation",
            action_key="channel_create",
            limit=cfg.channel_create_limit,
            window=cfg.channel_create_window,
            details=f"Created channel: **{channel.name}** (`{channel.id}`)",
        )

    # ─────────────────────────────────────────────
    # Mass Role Deletion
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        guild = role.guild
        cfg = self._nuke_cfg

        actor_id = await get_audit_user(
            guild, discord.AuditLogAction.role_delete
        )
        await self._handle_nuke_event(
            guild=guild,
            actor_id=actor_id,
            action_name="Mass Role Deletion",
            action_key="role_delete",
            limit=cfg.role_delete_limit,
            window=cfg.role_delete_window,
            details=f"Deleted role: **{role.name}** (`{role.id}`)",
        )

    # ─────────────────────────────────────────────
    # Mass Role Creation
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        guild = role.guild
        cfg = self._nuke_cfg

        actor_id = await get_audit_user(
            guild, discord.AuditLogAction.role_create
        )
        await self._handle_nuke_event(
            guild=guild,
            actor_id=actor_id,
            action_name="Mass Role Creation",
            action_key="role_create",
            limit=cfg.role_create_limit,
            window=cfg.role_create_window,
            details=f"Created role: **{role.name}**",
        )

    # ─────────────────────────────────────────────
    # Mass Bans
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: discord.User
    ) -> None:
        cfg = self._nuke_cfg

        actor_id = await get_audit_user(
            guild, discord.AuditLogAction.ban, target_id=user.id
        )
        await self._handle_nuke_event(
            guild=guild,
            actor_id=actor_id,
            action_name="Mass Ban",
            action_key="ban",
            limit=cfg.ban_limit,
            window=cfg.ban_window,
            details=f"Banned user: **{user}** (`{user.id}`)",
        )

    # ─────────────────────────────────────────────
    # Mass Kicks
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild
        cfg = self._nuke_cfg

        # Only detect if it was a kick (not a voluntary leave)
        actor_id = await get_audit_user(
            guild, discord.AuditLogAction.kick, target_id=member.id
        )
        if actor_id is None:
            return  # Voluntary leave, not a kick

        await self._handle_nuke_event(
            guild=guild,
            actor_id=actor_id,
            action_name="Mass Kick",
            action_key="kick",
            limit=cfg.kick_limit,
            window=cfg.kick_window,
            details=f"Kicked member: **{member}** (`{member.id}`)",
        )

    # ─────────────────────────────────────────────
    # Mass Webhook Creation
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.TextChannel) -> None:
        guild = channel.guild
        cfg = self._nuke_cfg

        actor_id = await get_audit_user(
            guild, discord.AuditLogAction.webhook_create
        )
        if actor_id is None:
            return

        await self._handle_nuke_event(
            guild=guild,
            actor_id=actor_id,
            action_name="Mass Webhook Creation",
            action_key="webhook_create",
            limit=cfg.webhook_create_limit,
            window=cfg.webhook_create_window,
            details=f"Webhook created in **{channel.name}**",
        )

    # ─────────────────────────────────────────────
    # Permission Escalation Detection
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> None:
        guild = before.guild

        # Check if administrator was granted
        if not before.permissions.administrator and after.permissions.administrator:
            actor_id = await get_audit_user(
                guild, discord.AuditLogAction.role_update
            )
            if actor_id and not await self.security.is_exempt(guild, actor_id):
                logger.warning(
                    f"[ANTI-NUKE] Permission escalation detected in {guild.name}: "
                    f"Role '{after.name}' gained admin by user {actor_id}"
                )

                # Ban attacker
                await self.security.punish_attacker(
                    guild,
                    actor_id,
                    f"Permission escalation: Granted Administrator to role '{after.name}'",
                )

                log_cog = self._get_logging_cog()
                if log_cog:
                    await log_cog.log_antinuke(
                        guild,
                        "Permission Escalation",
                        actor_id,
                        f"Granted **Administrator** to role **{after.name}**",
                    )

    # ─────────────────────────────────────────────
    # Bot Add Detection
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Detect suspicious bot additions."""
        if not member.bot:
            return  # Only care about bots

        guild = member.guild

        actor_id = await get_audit_user(
            guild, discord.AuditLogAction.bot_add, target_id=member.id
        )
        if actor_id is None:
            return

        # Check if actor is exempt
        if await self.security.is_exempt(guild, actor_id):
            logger.info(
                f"Whitelisted user {actor_id} added bot {member} to {guild.name}. Allowed."
            )
            return

        # Non-whitelisted user added a bot — kick the bot and warn
        try:
            await member.kick(
                reason=f"[ANTI-NUKE] Unauthorized bot addition by {actor_id}"
            )
            logger.warning(
                f"[ANTI-NUKE] Kicked unauthorized bot {member} added by {actor_id} in {guild.name}"
            )
        except discord.Forbidden:
            pass

        log_cog = self._get_logging_cog()
        if log_cog:
            await log_cog.log_antinuke(
                guild,
                "Unauthorized Bot Addition",
                actor_id,
                f"Attempted to add bot **{member}** (`{member.id}`)",
            )


async def setup(bot) -> None:
    await bot.add_cog(AntiNuke(bot))

"""
Logging System Cog - cogs/logging_system.py
Central logging cog. All other cogs send logs through this cog.
"""

import logging
from typing import Optional

import discord
from discord.ext import commands

from config import config
from utils.embeds import log_embed

logger = logging.getLogger(__name__)


class LoggingSystem(commands.Cog, name="Logging"):
    """
    Central logging system.
    Sends rich embeds to configured log channel.
    """

    def __init__(self, bot) -> None:
        self.bot = bot

    async def get_log_channel(
        self, guild_id: int
    ) -> Optional[discord.TextChannel]:
        """Fetch the configured log channel for a guild."""
        channel_id = await self.bot.db.get_log_channel(guild_id)
        if channel_id is None:
            return None
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return None
        return channel

    async def send_log(
        self,
        guild_id: int,
        embed: discord.Embed,
    ) -> None:
        """Send a log embed to the guild's log channel."""
        channel = await self.get_log_channel(guild_id)
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Cannot send log to channel in guild {guild_id}: Forbidden")
        except Exception as e:
            logger.error(f"Error sending log: {e}")

    # ─────────────────────────────────────────────
    # Moderation Logs
    # ─────────────────────────────────────────────

    async def log_mod_action(
        self,
        guild_id: int,
        action: str,
        target: discord.Member | discord.User,
        moderator: discord.Member,
        reason: Optional[str] = None,
        duration: Optional[str] = None,
    ) -> None:
        fields = [
            ("Target", f"{target.mention} (`{target.id}`)", True),
            ("Moderator", f"{moderator.mention} (`{moderator.id}`)", True),
            ("Reason", reason or "No reason provided", False),
        ]
        if duration:
            fields.insert(2, ("Duration", duration, True))

        embed = log_embed(
            title=f"🔨 Moderation: {action}",
            description=f"A moderation action was taken.",
            color=config.color_moderation,
            fields=fields,
            thumbnail_url=target.display_avatar.url,
        )
        await self.send_log(guild_id, embed)

    # ─────────────────────────────────────────────
    # Anti-Nuke Logs
    # ─────────────────────────────────────────────

    async def log_antinuke(
        self,
        guild: discord.Guild,
        action: str,
        attacker_id: int,
        details: str,
        count: Optional[int] = None,
    ) -> None:
        attacker = guild.get_member(attacker_id) or await self.bot.fetch_user(attacker_id)
        attacker_str = (
            f"{attacker.mention} (`{attacker_id}`)"
            if attacker
            else f"Unknown (`{attacker_id}`)"
        )
        fields = [
            ("Attacker", attacker_str, True),
            ("Guild", f"{guild.name} (`{guild.id}`)", True),
            ("Details", details, False),
        ]
        if count is not None:
            fields.append(("Events Detected", str(count), True))

        embed = log_embed(
            title="🚨 ANTI-NUKE TRIGGERED",
            description=f"**Action:** {action}",
            color=config.color_antinuke,
            fields=fields,
            footer="Attacker has been banned.",
        )
        await self.send_log(guild.id, embed)

    # ─────────────────────────────────────────────
    # Spam Logs
    # ─────────────────────────────────────────────

    async def log_spam(
        self,
        guild_id: int,
        user: discord.Member,
        action: str,
        channel: discord.TextChannel,
        reason: str,
    ) -> None:
        fields = [
            ("User", f"{user.mention} (`{user.id}`)", True),
            ("Channel", channel.mention, True),
            ("Action Taken", action, True),
            ("Reason", reason, False),
        ]
        embed = log_embed(
            title="🛡️ Spam Detected",
            description="Automatic spam detection triggered.",
            color=config.color_warning,
            fields=fields,
            thumbnail_url=user.display_avatar.url,
        )
        await self.send_log(guild_id, embed)

    # ─────────────────────────────────────────────
    # Server Event Logs
    # ─────────────────────────────────────────────

    async def log_role_update(
        self,
        guild_id: int,
        role: discord.Role,
        moderator_id: Optional[int],
        action: str,
        changes: Optional[str] = None,
    ) -> None:
        fields = [
            ("Role", f"{role.mention} (`{role.id}`)", True),
            ("Action", action, True),
        ]
        if moderator_id:
            fields.append(("By", f"<@{moderator_id}> (`{moderator_id}`)", True))
        if changes:
            fields.append(("Changes", changes, False))

        embed = log_embed(
            title="🎭 Role Updated",
            description=f"A role was {action.lower()}.",
            color=config.color_info,
            fields=fields,
        )
        await self.send_log(guild_id, embed)

    async def log_channel_update(
        self,
        guild_id: int,
        channel: discord.abc.GuildChannel,
        moderator_id: Optional[int],
        action: str,
    ) -> None:
        fields = [
            ("Channel", f"{channel.mention if hasattr(channel, 'mention') else channel.name} (`{channel.id}`)", True),
            ("Action", action, True),
        ]
        if moderator_id:
            fields.append(("By", f"<@{moderator_id}> (`{moderator_id}`)", True))

        embed = log_embed(
            title="📺 Channel Updated",
            description=f"A channel was {action.lower()}.",
            color=config.color_info,
            fields=fields,
        )
        await self.send_log(guild_id, embed)

    async def log_whitelist_change(
        self,
        guild_id: int,
        target_id: int,
        moderator_id: int,
        action: str,
    ) -> None:
        fields = [
            ("User", f"<@{target_id}> (`{target_id}`)", True),
            ("Action", action, True),
            ("By", f"<@{moderator_id}> (`{moderator_id}`)", True),
        ]
        embed = log_embed(
            title="📋 Whitelist Updated",
            description=f"Whitelist was modified.",
            color=config.color_info,
            fields=fields,
        )
        await self.send_log(guild_id, embed)

    # ─────────────────────────────────────────────
    # Discord Event Listeners for Auto-Logging
    # ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """Log bans that happen outside the bot."""
        fields = [
            ("User", f"{user.mention} (`{user.id}`)", True),
            ("Server", guild.name, True),
        ]
        embed = log_embed(
            title="🔨 Member Banned",
            description="A member was banned from the server.",
            color=config.color_error,
            fields=fields,
            thumbnail_url=user.display_avatar.url,
        )
        await self.send_log(guild.id, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Log member leaves/kicks."""
        fields = [
            ("User", f"{member.mention} (`{member.id}`)", True),
            ("Roles", ", ".join(r.mention for r in member.roles[1:]) or "None", False),
        ]
        embed = log_embed(
            title="👋 Member Left",
            description=f"**{member}** left or was removed from the server.",
            color=config.color_warning,
            fields=fields,
            thumbnail_url=member.display_avatar.url,
        )
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        embed = log_embed(
            title="🎭 Role Created",
            description=f"Role **{role.name}** was created.",
            color=config.color_success,
            fields=[("Role ID", str(role.id), True)],
        )
        await self.send_log(role.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        embed = log_embed(
            title="🗑️ Role Deleted",
            description=f"Role **{role.name}** was deleted.",
            color=config.color_error,
            fields=[("Role ID", str(role.id), True)],
        )
        await self.send_log(role.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        embed = log_embed(
            title="📺 Channel Created",
            description=f"Channel **{channel.name}** was created.",
            color=config.color_success,
            fields=[("Channel ID", str(channel.id), True), ("Type", str(channel.type), True)],
        )
        await self.send_log(channel.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        embed = log_embed(
            title="🗑️ Channel Deleted",
            description=f"Channel **{channel.name}** was deleted.",
            color=config.color_error,
            fields=[("Channel ID", str(channel.id), True), ("Type", str(channel.type), True)],
        )
        await self.send_log(channel.guild.id, embed)


async def setup(bot) -> None:
    await bot.add_cog(LoggingSystem(bot))

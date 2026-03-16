"""
Channel Protection - security/channel_protection.py
Monitors channel-level events for mass nuking, permission overwrites abuse,
and suspicious channel modifications.
"""

import logging

import discord
from discord.ext import commands

from core.rate_limiter import rate_limiter
from utils.helpers import get_audit_user

logger = logging.getLogger(__name__)


class ChannelProtection(commands.Cog, name="ChannelProtection"):
    """
    Monitors channel events for:
    - Mass channel deletion (nuking)
    - Mass channel creation (flooding)
    - Suspicious permission overwrites (locking everyone out)
    """

    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        """Detect suspicious permission overwrites."""
        guild = before.guild

        # Check if @everyone was denied all permissions
        everyone_role = guild.default_role
        before_ow = before.overwrites_for(everyone_role)
        after_ow = after.overwrites_for(everyone_role)

        # Detect if someone locked out @everyone from all text/voice perms
        if (
            not before_ow.read_messages
            and after_ow.read_messages is False
            and not before_ow.send_messages
            and after_ow.send_messages is False
        ):
            return  # Already locked, no change

        # Detect suspicious blanket deny of all permissions
        if after_ow.send_messages is False and after_ow.view_channel is False:
            actor_id = await get_audit_user(
                guild, discord.AuditLogAction.overwrite_update
            )
            if actor_id and not await self._is_exempt(guild, actor_id):
                logger.warning(
                    f"[CHANNEL-PROTECTION] Suspicious overwrite in {guild.name}: "
                    f"channel {after.name} locked by {actor_id}"
                )
                log_cog = self.bot.get_cog("Logging")
                if log_cog:
                    await log_cog.log_antinuke(
                        guild,
                        "Suspicious Channel Overwrite",
                        actor_id,
                        f"Channel **{after.name}** had @everyone locked out.",
                    )

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self, channel: discord.abc.GuildChannel
    ) -> None:
        """Track deletion rate per user for mass-nuke detection."""
        guild = channel.guild
        actor_id = await get_audit_user(guild, discord.AuditLogAction.channel_delete)
        if actor_id is None:
            return
        if await self._is_exempt(guild, actor_id):
            return

        exceeded, count = rate_limiter.check(
            guild.id, actor_id, "ch_del_secondary", limit=3, window=10
        )
        if exceeded:
            logger.warning(
                f"[CHANNEL-PROTECTION] Mass channel delete in {guild.name}: "
                f"actor {actor_id} deleted {count} channels"
            )

    async def _is_exempt(self, guild: discord.Guild, user_id: int) -> bool:
        if user_id == guild.owner_id:
            return True
        return await self.bot.db.is_whitelisted(guild.id, user_id)


async def setup(bot) -> None:
    await bot.add_cog(ChannelProtection(bot))

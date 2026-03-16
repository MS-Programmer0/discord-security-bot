"""
Anti Bot Add - security/anti_bot_add.py
Detects and blocks unauthorized bot additions.
Only whitelisted users and the guild owner can add bots.
"""

import logging
from typing import Optional

import discord
from discord.ext import commands

from utils.helpers import get_audit_user

logger = logging.getLogger(__name__)


class AntiBotAdd(commands.Cog, name="AntiBotAdd"):
    """
    Prevents unauthorized bot additions to the guild.
    If a non-whitelisted, non-owner user adds a bot:
      - The bot is immediately kicked
      - The actor is warned or banned depending on severity
    """

    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Check every new bot joining the server."""
        if not member.bot:
            return  # Only process bots

        guild = member.guild

        # Fetch the actor from the audit log
        actor_id = await get_audit_user(
            guild,
            discord.AuditLogAction.bot_add,
            target_id=member.id,
            limit=3,
        )

        if actor_id is None:
            logger.warning(
                f"[ANTI-BOT-ADD] Cannot determine who added bot {member} to {guild.name}"
            )
            return

        # Our own bot joining — always allowed
        if actor_id == self.bot.user.id:
            return

        # Guild owner — always allowed
        if actor_id == guild.owner_id:
            logger.info(
                f"[ANTI-BOT-ADD] Guild owner added bot {member} to {guild.name}. Allowed."
            )
            return

        # Check whitelist
        is_wl = await self.bot.db.is_whitelisted(guild.id, actor_id)
        if is_wl:
            logger.info(
                f"[ANTI-BOT-ADD] Whitelisted user {actor_id} added bot {member} to {guild.name}. Allowed."
            )
            return

        # Unauthorized bot addition — kick the added bot
        logger.warning(
            f"[ANTI-BOT-ADD] Unauthorized bot addition detected in {guild.name}: "
            f"bot={member} ({member.id}), actor={actor_id}"
        )

        kicked = False
        try:
            await member.kick(
                reason=f"[ANTI-BOT-ADD] Unauthorized bot addition by user {actor_id}"
            )
            kicked = True
            logger.info(f"[ANTI-BOT-ADD] Kicked unauthorized bot {member} from {guild.name}")
        except discord.Forbidden:
            logger.error(f"[ANTI-BOT-ADD] Cannot kick bot {member}: Forbidden")

        # Log the event
        log_cog = self.bot.get_cog("Logging")
        if log_cog:
            await log_cog.log_antinuke(
                guild,
                "Unauthorized Bot Addition",
                actor_id,
                f"Attempted to add bot **{member}** (`{member.id}`). "
                f"Bot {'was kicked' if kicked else 'could not be kicked'}.",
            )

        # Warn the actor in DM if possible
        actor = guild.get_member(actor_id)
        if actor:
            try:
                warn_embed = discord.Embed(
                    title="⚠️ Unauthorized Bot Addition",
                    description=(
                        f"You attempted to add a bot to **{guild.name}** without authorization.\n"
                        "Only whitelisted users can add bots to this server.\n"
                        "Repeat violations will result in a ban."
                    ),
                    color=0xF39C12,
                )
                await actor.send(embed=warn_embed)
            except discord.Forbidden:
                pass


async def setup(bot) -> None:
    await bot.add_cog(AntiBotAdd(bot))

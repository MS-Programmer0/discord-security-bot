"""
Spam Protection Cog - cogs/spam_protection.py
High-performance spam detection using sliding window rate limiting.
Detects: message spam, mention spam, link spam, emoji spam, duplicate spam.
"""

import asyncio
import logging
import re
from collections import defaultdict, deque
from typing import Dict, Optional

import discord
from discord.ext import commands

from config import config
from core.rate_limiter import SlidingWindowRateLimiter
from utils.embeds import spam_alert_embed
from utils.helpers import (
    contains_url,
    count_emojis,
    count_mentions,
)

logger = logging.getLogger(__name__)


class SpamProtection(commands.Cog, name="SpamProtection"):
    """
    Multi-layer spam detection and prevention.
    Works independently from anti-nuke; applies to all users including whitelisted.
    Moderators (kick_members perm) are exempt.
    """

    def __init__(self, bot) -> None:
        self.bot = bot
        self.rl = SlidingWindowRateLimiter()

        # Track recent message content for duplicate detection
        # {guild_id: {user_id: deque of recent message contents}}
        self._recent_messages: Dict[int, Dict[int, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=10))
        )

        # Users currently being processed (prevents concurrent spam action)
        self._processing: set = set()

    def _is_exempt(self, member: discord.Member) -> bool:
        """
        Check if member is exempt from spam detection.
        Moderators (kick/ban perms) are exempt. Whitelisted users are NOT exempt from spam.
        """
        if member.bot:
            return True
        return (
            member.guild_permissions.kick_members
            or member.guild_permissions.ban_members
            or member.guild_permissions.administrator
        )

    async def _get_spam_settings(self, guild_id: int) -> dict:
        """Get spam settings from DB or return defaults."""
        try:
            return await self.bot.db.get_spam_settings(guild_id)
        except Exception:
            return {
                "warn_message_count": config.spam.warn_message_count,
                "warn_message_window": config.spam.warn_message_window,
                "mute_message_count": config.spam.mute_message_count,
                "mute_message_window": config.spam.mute_message_window,
                "kick_message_count": config.spam.kick_message_count,
                "kick_message_window": config.spam.kick_message_window,
                "mute_duration": config.spam.mute_duration,
            }

    async def _apply_spam_action(
        self,
        member: discord.Member,
        channel: discord.TextChannel,
        action: str,
        reason: str,
    ) -> None:
        """
        Apply spam punishment.
        Actions: warn, mute, kick
        """
        key = (member.guild.id, member.id)
        if key in self._processing:
            return
        self._processing.add(key)

        try:
            settings = await self._get_spam_settings(member.guild.id)

            if action == "warn":
                # Send warning in channel
                try:
                    warn_embed = discord.Embed(
                        title="⚠️ Spam Warning",
                        description=f"{member.mention}, please slow down! {reason}",
                        color=config.color_warning,
                    )
                    await channel.send(embed=warn_embed, delete_after=8)
                except discord.Forbidden:
                    pass

            elif action == "mute":
                # Apply Discord native timeout
                duration_secs = settings.get("mute_duration", 300)
                try:
                    from datetime import timedelta
                    await member.timeout(
                        timedelta(seconds=duration_secs),
                        reason=f"[AUTO-SPAM] {reason}",
                    )
                    mute_embed = discord.Embed(
                        title="🔇 Auto-Muted",
                        description=f"{member.mention} has been muted for **{duration_secs}s** due to spam.",
                        color=config.color_error,
                    )
                    await channel.send(embed=mute_embed, delete_after=10)
                except discord.Forbidden:
                    logger.warning(
                        f"Cannot mute {member} in {member.guild.name}: Forbidden"
                    )

            elif action == "kick":
                try:
                    await member.kick(reason=f"[AUTO-SPAM] {reason}")
                    kick_embed = discord.Embed(
                        title="👢 Auto-Kicked",
                        description=f"{member.mention} was kicked for excessive spam.",
                        color=config.color_error,
                    )
                    await channel.send(embed=kick_embed, delete_after=10)
                except discord.Forbidden:
                    logger.warning(
                        f"Cannot kick {member} in {member.guild.name}: Forbidden"
                    )

            # Log spam action
            log_cog = self.bot.get_cog("Logging")
            if log_cog:
                await log_cog.log_spam(
                    member.guild.id, member, action.upper(), channel, reason
                )

            # Log to database
            await self.bot.db.log_mod_action(
                member.guild.id,
                member.id,
                self.bot.user.id,
                f"spam_{action}",
                reason,
            )

        finally:
            self._processing.discard(key)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Main spam detection event listener.
        Checks for: message rate, mention spam, link spam, emoji spam, duplicates.
        """
        # Skip DMs, system messages
        if not message.guild or not isinstance(message.author, discord.Member):
            return

        # Skip exempt users (mods/bots)
        if self._is_exempt(message.author):
            return

        # Check if spam detection is enabled for this guild
        guild_settings = await self.bot.db.get_guild_settings(message.guild.id)
        if guild_settings and not guild_settings.get("spam_enabled", 1):
            return

        member = message.author
        guild_id = message.guild.id
        user_id = member.id
        channel = message.channel
        settings = await self._get_spam_settings(guild_id)

        # ── 1. Message Rate Check ──────────────────
        # Warn threshold
        warn_exceeded, warn_count = self.rl.check(
            guild_id, user_id, "msg_warn",
            settings["warn_message_count"],
            settings["warn_message_window"],
        )

        # Mute threshold
        mute_exceeded, mute_count = self.rl.check(
            guild_id, user_id, "msg_mute",
            settings["mute_message_count"],
            settings["mute_message_window"],
        )

        # Kick threshold
        kick_exceeded, kick_count = self.rl.check(
            guild_id, user_id, "msg_kick",
            settings["kick_message_count"],
            settings["kick_message_window"],
        )

        if kick_exceeded:
            await self._apply_spam_action(
                member, channel, "kick",
                f"Extreme message spam ({kick_count} messages/{settings['kick_message_window']}s)",
            )
            return
        elif mute_exceeded:
            await self._apply_spam_action(
                member, channel, "mute",
                f"Message spam ({mute_count} messages/{settings['mute_message_window']}s)",
            )
            return
        elif warn_exceeded:
            await self._apply_spam_action(
                member, channel, "warn",
                f"Slow down! Sending too many messages.",
            )

        # ── 2. Mention Spam Check ──────────────────
        mention_count_in_msg = count_mentions(message)
        if mention_count_in_msg > 0:
            men_exceeded, men_total = self.rl.check(
                guild_id, user_id, "mentions",
                config.spam.mention_limit,
                config.spam.mention_window,
            )
            if men_exceeded or mention_count_in_msg >= config.spam.mention_limit:
                await self._apply_spam_action(
                    member, channel, "mute",
                    f"Mass mention spam ({mention_count_in_msg} mentions in one message / {men_total} total)",
                )
                return

        # ── 3. Link Spam Check ─────────────────────
        if contains_url(message.content):
            link_exceeded, _ = self.rl.check(
                guild_id, user_id, "links",
                config.spam.link_limit,
                config.spam.link_window,
            )
            if link_exceeded:
                await self._apply_spam_action(
                    member, channel, "mute",
                    f"Link spam detected",
                )
                return

        # ── 4. Emoji Spam Check ────────────────────
        emoji_count = count_emojis(message.content)
        if emoji_count >= config.spam.emoji_limit:
            emoji_exceeded, _ = self.rl.check(
                guild_id, user_id, "emojis",
                config.spam.emoji_limit,
                config.spam.emoji_window,
            )
            if emoji_exceeded:
                await self._apply_spam_action(
                    member, channel, "warn",
                    f"Emoji spam detected ({emoji_count} emojis in message)",
                )

        # ── 5. Duplicate Message Check ─────────────
        content = message.content.strip().lower()
        if content:
            recent = self._recent_messages[guild_id][user_id]
            duplicate_count = sum(1 for m in recent if m == content)
            recent.append(content)

            if duplicate_count >= config.spam.duplicate_limit - 1:
                dup_exceeded, _ = self.rl.check(
                    guild_id, user_id, "duplicates",
                    config.spam.duplicate_limit,
                    config.spam.duplicate_window,
                )
                if dup_exceeded:
                    await self._apply_spam_action(
                        member, channel, "mute",
                        "Duplicate message spam detected",
                    )


async def setup(bot) -> None:
    await bot.add_cog(SpamProtection(bot))

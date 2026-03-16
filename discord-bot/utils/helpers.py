"""
Helpers - utils/helpers.py
General-purpose utility functions used across cogs.
"""

import re
from datetime import timedelta
from typing import Optional, Union

import discord


# ─────────────────────────────────────────────
# Duration Parsing
# ─────────────────────────────────────────────

DURATION_REGEX = re.compile(
    r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", re.IGNORECASE
)


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """
    Parse a duration string like "1d2h30m" into a timedelta.
    Returns None if parsing fails.
    """
    match = DURATION_REGEX.fullmatch(duration_str.strip())
    if not match or not any(match.groups()):
        return None

    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)

    total = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

    # Discord timeout max is 28 days
    if total.total_seconds() <= 0 or total.days > 28:
        return None

    return total


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    elif seconds < 86400:
        h, rem = divmod(seconds, 3600)
        m = rem // 60
        return f"{h}h {m}m"
    else:
        d, rem = divmod(seconds, 86400)
        h = rem // 3600
        return f"{d}d {h}h"


# ─────────────────────────────────────────────
# Discord Helpers
# ─────────────────────────────────────────────

async def get_or_fetch_member(
    guild: discord.Guild, user_id: int
) -> Optional[discord.Member]:
    """Get member from cache or fetch from API."""
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except (discord.NotFound, discord.HTTPException):
            pass
    return member


async def get_or_fetch_user(
    bot: discord.Client, user_id: int
) -> Optional[discord.User]:
    """Get user from cache or fetch from API."""
    user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            pass
    return user


async def safe_send(
    channel: discord.abc.Messageable,
    content: Optional[str] = None,
    **kwargs,
) -> Optional[discord.Message]:
    """Send a message, suppressing errors."""
    try:
        return await channel.send(content, **kwargs)
    except (discord.Forbidden, discord.HTTPException):
        return None


async def safe_respond(
    interaction: discord.Interaction,
    *args,
    ephemeral: bool = False,
    **kwargs,
) -> None:
    """Respond to an interaction, handling already-responded state."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(*args, ephemeral=ephemeral, **kwargs)
        else:
            await interaction.response.send_message(
                *args, ephemeral=ephemeral, **kwargs
            )
    except Exception:
        pass


# ─────────────────────────────────────────────
# Content Checks
# ─────────────────────────────────────────────

URL_REGEX = re.compile(
    r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?"
)

INVITE_REGEX = re.compile(
    r"(?:discord(?:\.gg|app\.com/invite|\.com/invite)/[\w-]+)"
)


def contains_url(text: str) -> bool:
    return bool(URL_REGEX.search(text))


def contains_invite(text: str) -> bool:
    return bool(INVITE_REGEX.search(text))


def count_mentions(message: discord.Message) -> int:
    return len(message.mentions) + len(message.role_mentions)


def count_emojis(text: str) -> int:
    """Count Unicode and custom Discord emojis."""
    custom = re.findall(r"<a?:[a-zA-Z0-9_]+:\d+>", text)
    # Simple unicode emoji detection (common ranges)
    unicode_emojis = re.findall(
        "[\U0001F300-\U0001F9FF\U00002600-\U000027BF]+", text
    )
    return len(custom) + sum(len(e) for e in unicode_emojis)


def is_mass_mention(message: discord.Message, threshold: int = 5) -> bool:
    return count_mentions(message) >= threshold


# ─────────────────────────────────────────────
# Audit Log Helpers
# ─────────────────────────────────────────────

async def get_audit_user(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: Optional[int] = None,
    limit: int = 5,
) -> Optional[int]:
    """
    Fetch the most recent audit log entry user for an action.
    Returns the user ID of the actor, or None if unavailable.
    """
    try:
        async for entry in guild.audit_logs(action=action, limit=limit):
            if target_id is None or (entry.target and entry.target.id == target_id):
                return entry.user.id if entry.user else None
    except (discord.Forbidden, discord.HTTPException):
        pass
    return None

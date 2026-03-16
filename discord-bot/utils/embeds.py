"""
Embed Utilities - utils/embeds.py
Reusable Discord embed builders for consistent UI across the bot.
"""

from datetime import datetime
from typing import Optional

import discord

from config import config


def _now() -> datetime:
    return datetime.utcnow()


def success_embed(
    description: str,
    title: Optional[str] = None,
    *,
    footer: Optional[str] = None,
) -> discord.Embed:
    e = discord.Embed(
        title=title or "✅ Success",
        description=description,
        color=config.color_success,
        timestamp=_now(),
    )
    if footer:
        e.set_footer(text=footer)
    return e


def error_embed(
    description: str,
    title: Optional[str] = None,
) -> discord.Embed:
    return discord.Embed(
        title=title or "❌ Error",
        description=description,
        color=config.color_error,
        timestamp=_now(),
    )


def warning_embed(
    description: str,
    title: Optional[str] = None,
) -> discord.Embed:
    return discord.Embed(
        title=title or "⚠️ Warning",
        description=description,
        color=config.color_warning,
        timestamp=_now(),
    )


def info_embed(
    description: str,
    title: Optional[str] = None,
) -> discord.Embed:
    return discord.Embed(
        title=title or "ℹ️ Information",
        description=description,
        color=config.color_info,
        timestamp=_now(),
    )


def moderation_embed(
    action: str,
    target: discord.Member | discord.User,
    moderator: discord.Member,
    reason: Optional[str] = None,
    *,
    duration: Optional[str] = None,
    extra_fields: Optional[list] = None,
) -> discord.Embed:
    """Standard moderation action embed."""
    e = discord.Embed(
        title=f"🔨 {action}",
        color=config.color_moderation,
        timestamp=_now(),
    )
    e.add_field(name="Target", value=f"{target.mention} (`{target.id}`)", inline=True)
    e.add_field(
        name="Moderator", value=f"{moderator.mention} (`{moderator.id}`)", inline=True
    )
    if duration:
        e.add_field(name="Duration", value=duration, inline=True)
    e.add_field(name="Reason", value=reason or "No reason provided", inline=False)

    if extra_fields:
        for name, value, inline in extra_fields:
            e.add_field(name=name, value=value, inline=inline)

    e.set_thumbnail(url=target.display_avatar.url)
    return e


def antinuke_alert_embed(
    action: str,
    attacker: discord.Member | discord.User | None,
    attacker_id: int,
    guild: discord.Guild,
    details: str,
    count: Optional[int] = None,
) -> discord.Embed:
    """High-visibility anti-nuke alert embed."""
    e = discord.Embed(
        title="🚨 ANTI-NUKE TRIGGERED",
        description=f"**Action:** {action}\n**Details:** {details}",
        color=config.color_antinuke,
        timestamp=_now(),
    )
    attacker_str = (
        f"{attacker.mention} (`{attacker_id}`)"
        if attacker
        else f"Unknown User (`{attacker_id}`)"
    )
    e.add_field(name="Attacker", value=attacker_str, inline=True)
    e.add_field(name="Server", value=f"{guild.name} (`{guild.id}`)", inline=True)
    if count is not None:
        e.add_field(name="Events Detected", value=str(count), inline=True)
    e.set_footer(text="Attacker has been banned.")
    return e


def spam_alert_embed(
    user: discord.Member,
    action: str,
    channel: discord.TextChannel,
    reason: str,
) -> discord.Embed:
    e = discord.Embed(
        title=f"🛡️ Spam Detection: {action}",
        description=reason,
        color=config.color_warning,
        timestamp=_now(),
    )
    e.add_field(name="User", value=f"{user.mention} (`{user.id}`)", inline=True)
    e.add_field(name="Channel", value=channel.mention, inline=True)
    e.set_thumbnail(url=user.display_avatar.url)
    return e


def log_embed(
    title: str,
    description: str,
    color: int,
    fields: Optional[list] = None,
    *,
    footer: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
) -> discord.Embed:
    """Generic log embed for the logging system."""
    e = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=_now(),
    )
    if fields:
        for name, value, inline in fields:
            e.add_field(name=name, value=str(value)[:1024], inline=inline)
    if footer:
        e.set_footer(text=footer)
    if thumbnail_url:
        e.set_thumbnail(url=thumbnail_url)
    return e

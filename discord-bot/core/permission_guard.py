"""
Permission Guard - core/permission_guard.py
Centralized permission checking for commands and anti-nuke bypass.
"""

import logging
from typing import Optional

import discord
from discord import app_commands

logger = logging.getLogger(__name__)


class PermissionGuard:
    """
    Centralized permission validation.
    Used by moderation commands to validate executor authority.
    """

    @staticmethod
    def is_owner(bot_owner_id: Optional[int], user_id: int) -> bool:
        return bot_owner_id is not None and user_id == bot_owner_id

    @staticmethod
    def can_moderate(
        moderator: discord.Member,
        target: discord.Member,
    ) -> tuple[bool, str]:
        """
        Check if moderator can act on target.
        Returns (allowed: bool, reason: str).
        """
        guild = moderator.guild

        # Cannot moderate the guild owner
        if target.id == guild.owner_id:
            return False, "Cannot moderate the server owner."

        # Cannot moderate yourself
        if moderator.id == target.id:
            return False, "You cannot moderate yourself."

        # Bot's highest role must be above target's highest role
        if guild.me.top_role <= target.top_role:
            return False, "My role is not high enough to moderate this user."

        # Moderator's highest role must be above target's highest role
        if moderator.top_role <= target.top_role:
            return False, "Your role is not high enough to moderate this user."

        return True, "OK"

    @staticmethod
    def has_mod_permissions(member: discord.Member) -> bool:
        """Check if member has basic moderation permissions."""
        return (
            member.guild_permissions.kick_members
            or member.guild_permissions.ban_members
            or member.guild_permissions.manage_messages
            or member.guild_permissions.administrator
        )

    @staticmethod
    def is_admin(member: discord.Member) -> bool:
        return member.guild_permissions.administrator

    @staticmethod
    def bot_has_permissions(guild: discord.Guild, **perms) -> tuple[bool, list[str]]:
        """Check if the bot has required permissions in the guild."""
        me = guild.me
        missing = []
        for perm, value in perms.items():
            if getattr(me.guild_permissions, perm, False) != value:
                missing.append(perm)
        return len(missing) == 0, missing


# ─────────────────────────────────────────────
# App command permission decorators
# ─────────────────────────────────────────────

def require_mod():
    """Decorator: requires kick_members or ban_members."""
    return app_commands.checks.has_permissions(kick_members=True)


def require_admin():
    """Decorator: requires administrator."""
    return app_commands.checks.has_permissions(administrator=True)


def require_manage_guild():
    """Decorator: requires manage_guild."""
    return app_commands.checks.has_permissions(manage_guild=True)

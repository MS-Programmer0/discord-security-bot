"""
Cooldowns - utils/cooldowns.py
Custom cooldown decorators and helpers for slash commands.
"""

import time
from collections import defaultdict
from functools import wraps
from typing import Callable, Dict, Optional

import discord
from discord import app_commands


class CooldownManager:
    """
    Per-user, per-guild command cooldown manager.
    Used as a fallback when discord.py's built-in cooldown isn't granular enough.
    """

    def __init__(self) -> None:
        # {(guild_id, user_id, command): last_used_timestamp}
        self._cooldowns: Dict[tuple, float] = defaultdict(float)

    def check(
        self,
        guild_id: int,
        user_id: int,
        command: str,
        cooldown: float,
    ) -> Optional[float]:
        """
        Check if user is on cooldown.
        Returns remaining cooldown seconds, or None if not on cooldown.
        """
        key = (guild_id, user_id, command)
        last_used = self._cooldowns[key]
        now = time.monotonic()
        remaining = cooldown - (now - last_used)

        if remaining > 0:
            return remaining
        return None

    def use(
        self,
        guild_id: int,
        user_id: int,
        command: str,
    ) -> None:
        """Record command usage."""
        self._cooldowns[(guild_id, user_id, command)] = time.monotonic()

    def reset(
        self,
        guild_id: int,
        user_id: int,
        command: str,
    ) -> None:
        """Reset cooldown for user."""
        key = (guild_id, user_id, command)
        self._cooldowns.pop(key, None)


# Global cooldown manager instance
cooldown_manager = CooldownManager()


def slash_cooldown(seconds: float, bypass_admin: bool = True):
    """
    App command cooldown decorator.
    Optionally bypasses for admins.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            # Admins bypass cooldown
            if (
                bypass_admin
                and interaction.user.guild_permissions.administrator
            ):
                return await func(self, interaction, *args, **kwargs)

            remaining = cooldown_manager.check(
                interaction.guild_id,
                interaction.user.id,
                func.__name__,
                seconds,
            )
            if remaining:
                from utils.embeds import error_embed
                await interaction.response.send_message(
                    embed=error_embed(
                        f"Command on cooldown. Please wait **{remaining:.1f}s**."
                    ),
                    ephemeral=True,
                )
                return

            cooldown_manager.use(
                interaction.guild_id, interaction.user.id, func.__name__
            )
            return await func(self, interaction, *args, **kwargs)

        return wrapper

    return decorator

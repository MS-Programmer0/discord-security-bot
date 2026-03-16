"""
Role Protection - security/role_protection.py
Monitors role permission changes and mass role edits.
Detects: admin escalation, mass permission grants, dangerous role modifications.
"""

import logging
from typing import Optional

import discord
from discord.ext import commands

from core.rate_limiter import rate_limiter
from utils.helpers import get_audit_user

logger = logging.getLogger(__name__)

# Dangerous permissions to watch for escalation
DANGEROUS_PERMISSIONS = [
    "administrator",
    "ban_members",
    "kick_members",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "manage_webhooks",
]


class RoleProtection(commands.Cog, name="RoleProtection"):
    """
    Monitors role updates for:
    - Administrator permission grants
    - Dangerous permission escalation
    - Mass role edits (rate limited)
    - Role hoisting above bot's role
    """

    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_role_update(
        self, before: discord.Role, after: discord.Role
    ) -> None:
        guild = before.guild

        # Detect dangerous permission additions
        await self._check_permission_escalation(guild, before, after)

        # Detect mass role edits
        await self._check_mass_role_edit(guild, before, after)

    async def _check_permission_escalation(
        self,
        guild: discord.Guild,
        before: discord.Role,
        after: discord.Role,
    ) -> None:
        """Detect when a role gains dangerous permissions."""
        before_perms = before.permissions
        after_perms = after.permissions

        gained = []
        for perm in DANGEROUS_PERMISSIONS:
            if not getattr(before_perms, perm, False) and getattr(after_perms, perm, False):
                gained.append(perm)

        if not gained:
            return

        actor_id = await get_audit_user(guild, discord.AuditLogAction.role_update)
        if actor_id is None:
            return

        # Skip if exempt
        is_exempt = False
        if actor_id == guild.owner_id:
            is_exempt = True
        else:
            is_exempt = await self.bot.db.is_whitelisted(guild.id, actor_id)

        if is_exempt:
            return

        logger.warning(
            f"[ROLE-PROTECTION] Permission escalation in {guild.name}: "
            f"Role '{after.name}' gained {gained} by actor {actor_id}"
        )

        # Log the escalation
        log_cog = self.bot.get_cog("Logging")
        if log_cog:
            await log_cog.log_antinuke(
                guild,
                "Permission Escalation",
                actor_id,
                f"Role **{after.name}** gained dangerous permissions: `{'`, `'.join(gained)}`",
            )

        # If administrator was granted — ban immediately
        if "administrator" in gained:
            antinuke_cog = self.bot.get_cog("AntiNuke")
            if antinuke_cog:
                await antinuke_cog.security.punish_attacker(
                    guild,
                    actor_id,
                    f"Granted administrator to role '{after.name}'",
                )

    async def _check_mass_role_edit(
        self,
        guild: discord.Guild,
        before: discord.Role,
        after: discord.Role,
    ) -> None:
        """Detect mass role edits (many roles edited in quick succession)."""
        actor_id = await get_audit_user(guild, discord.AuditLogAction.role_update)
        if actor_id is None:
            return

        # Skip exempt
        if actor_id == guild.owner_id:
            return
        if await self.bot.db.is_whitelisted(guild.id, actor_id):
            return

        exceeded, count = rate_limiter.check(
            guild.id, actor_id, "role_edit", limit=5, window=10
        )
        if exceeded:
            logger.warning(
                f"[ROLE-PROTECTION] Mass role edit in {guild.name}: "
                f"actor {actor_id} edited {count} roles in 10s"
            )
            log_cog = self.bot.get_cog("Logging")
            if log_cog:
                await log_cog.log_antinuke(
                    guild,
                    "Mass Role Edit",
                    actor_id,
                    f"Edited **{count}** roles in 10 seconds.",
                )


async def setup(bot) -> None:
    await bot.add_cog(RoleProtection(bot))

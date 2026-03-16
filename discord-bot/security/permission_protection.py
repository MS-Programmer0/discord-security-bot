"""
Permission Protection - security/permission_protection.py
Detects when users attempt to grant themselves or others admin/dangerous permissions
outside of normal whitelisted workflows.
"""

import logging

import discord
from discord.ext import commands

from utils.helpers import get_audit_user

logger = logging.getLogger(__name__)

# Permissions that should never be self-granted
CRITICAL_PERMISSIONS = {
    "administrator",
    "manage_guild",
    "ban_members",
    "kick_members",
    "manage_roles",
}


class PermissionProtection(commands.Cog, name="PermissionProtection"):
    """
    Monitors member permission changes and guild-level permission updates.
    Detects self-granting of critical permissions.
    """

    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """Detect if a member gained roles with critical permissions."""
        guild = before.guild

        # Find newly gained roles
        gained_roles = set(after.roles) - set(before.roles)
        if not gained_roles:
            return

        # Check if any gained role has critical permissions
        critical_gained = []
        for role in gained_roles:
            for perm in CRITICAL_PERMISSIONS:
                if getattr(role.permissions, perm, False):
                    critical_gained.append((role, perm))

        if not critical_gained:
            return

        # Get the actor (who assigned the role)
        actor_id = await get_audit_user(
            guild,
            discord.AuditLogAction.member_role_update,
            target_id=after.id,
        )
        if actor_id is None:
            return

        # Skip exempt actors
        if actor_id == guild.owner_id:
            return
        if await self.bot.db.is_whitelisted(guild.id, actor_id):
            return

        # Detect self-grant (actor == target)
        is_self_grant = actor_id == after.id

        for role, perm in critical_gained:
            action_type = "Self-Permission Grant" if is_self_grant else "Unauthorized Permission Grant"
            details = (
                f"{'Self-assigned' if is_self_grant else 'Assigned'} role **{role.name}** "
                f"(has `{perm}`) to **{after}** (`{after.id}`)"
            )

            logger.warning(
                f"[PERM-PROTECTION] {action_type} in {guild.name}: "
                f"actor={actor_id}, target={after.id}, role={role.name}, perm={perm}"
            )

            log_cog = self.bot.get_cog("Logging")
            if log_cog:
                await log_cog.log_antinuke(
                    guild,
                    action_type,
                    actor_id,
                    details,
                )

            # If self-grant of administrator — immediately ban
            if is_self_grant and perm == "administrator":
                antinuke = self.bot.get_cog("AntiNuke")
                if antinuke:
                    await antinuke.security.punish_attacker(
                        guild,
                        actor_id,
                        f"Self-granted administrator via role '{role.name}'",
                    )
                break  # Banned, no need to continue

    @commands.Cog.listener()
    async def on_guild_update(
        self, before: discord.Guild, after: discord.Guild
    ) -> None:
        """Detect suspicious guild-level changes."""
        guild = after

        actor_id = await get_audit_user(guild, discord.AuditLogAction.guild_update)
        if actor_id is None:
            return
        if actor_id == guild.owner_id:
            return
        if await self.bot.db.is_whitelisted(guild.id, actor_id):
            return

        changes = []

        # Detect verification level being lowered (potential raid preparation)
        if before.verification_level > after.verification_level:
            changes.append(
                f"Verification level lowered: {before.verification_level} → {after.verification_level}"
            )

        # Detect 2FA requirement being disabled
        if before.mfa_level != after.mfa_level and after.mfa_level == discord.MFALevel.disabled:
            changes.append("2FA requirement disabled")

        if changes:
            logger.warning(
                f"[PERM-PROTECTION] Suspicious guild update in {guild.name} by {actor_id}: "
                + " | ".join(changes)
            )
            log_cog = self.bot.get_cog("Logging")
            if log_cog:
                await log_cog.log_antinuke(
                    guild,
                    "Suspicious Guild Update",
                    actor_id,
                    "\n".join(changes),
                )


async def setup(bot) -> None:
    await bot.add_cog(PermissionProtection(bot))

"""
Moderation Cog - cogs/moderation.py
Full moderation command suite using slash commands.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from core.permission_guard import PermissionGuard
from utils.embeds import (
    success_embed,
    error_embed,
    moderation_embed,
)
from utils.helpers import (
    parse_duration,
    format_duration,
    safe_respond,
    get_or_fetch_member,
)
from utils.cooldowns import slash_cooldown

logger = logging.getLogger(__name__)


class Moderation(commands.Cog, name="Moderation"):
    """
    Full moderation suite.
    Handles bans, kicks, mutes, warnings, channel management, and more.
    """

    def __init__(self, bot) -> None:
        self.bot = bot
        self.guard = PermissionGuard()

    def _get_logging_cog(self):
        return self.bot.get_cog("Logging")

    # ─────────────────────────────────────────────
    # /ban
    # ─────────────────────────────────────────────

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for the ban",
        delete_days="Days of messages to delete (0-7)",
    )
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        allowed, msg = self.guard.can_moderate(interaction.user, member)
        if not allowed:
            await interaction.response.send_message(
                embed=error_embed(msg), ephemeral=True
            )
            return

        reason_str = reason or "No reason provided"

        try:
            await member.ban(
                reason=f"[{interaction.user}] {reason_str}",
                delete_message_days=delete_days,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("I don't have permission to ban this member."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=moderation_embed("Ban", member, interaction.user, reason_str)
        )

        # Log to database and logging cog
        await self.bot.db.log_mod_action(
            interaction.guild_id, member.id, interaction.user.id, "ban", reason_str
        )
        log_cog = self._get_logging_cog()
        if log_cog:
            await log_cog.log_mod_action(
                interaction.guild_id, "Ban", member, interaction.user, reason_str
            )

    # ─────────────────────────────────────────────
    # /kick
    # ─────────────────────────────────────────────

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        allowed, msg = self.guard.can_moderate(interaction.user, member)
        if not allowed:
            await interaction.response.send_message(
                embed=error_embed(msg), ephemeral=True
            )
            return

        reason_str = reason or "No reason provided"

        try:
            await member.kick(reason=f"[{interaction.user}] {reason_str}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("I don't have permission to kick this member."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=moderation_embed("Kick", member, interaction.user, reason_str)
        )
        await self.bot.db.log_mod_action(
            interaction.guild_id, member.id, interaction.user.id, "kick", reason_str
        )
        log_cog = self._get_logging_cog()
        if log_cog:
            await log_cog.log_mod_action(
                interaction.guild_id, "Kick", member, interaction.user, reason_str
            )

    # ─────────────────────────────────────────────
    # /timeout (Discord native timeout)
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="timeout", description="Timeout (mute) a member for a duration."
    )
    @app_commands.describe(
        member="The member to timeout",
        duration="Duration (e.g. 10m, 1h, 1d)",
        reason="Reason for the timeout",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: Optional[str] = None,
    ) -> None:
        allowed, msg = self.guard.can_moderate(interaction.user, member)
        if not allowed:
            await interaction.response.send_message(
                embed=error_embed(msg), ephemeral=True
            )
            return

        td = parse_duration(duration)
        if td is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Invalid duration format. Use: `10s`, `5m`, `1h`, `1d` (max 28d)."
                ),
                ephemeral=True,
            )
            return

        reason_str = reason or "No reason provided"

        try:
            await member.timeout(td, reason=f"[{interaction.user}] {reason_str}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("I don't have permission to timeout this member."),
                ephemeral=True,
            )
            return

        duration_str = format_duration(int(td.total_seconds()))
        await interaction.response.send_message(
            embed=moderation_embed(
                "Timeout",
                member,
                interaction.user,
                reason_str,
                duration=duration_str,
            )
        )
        await self.bot.db.log_mod_action(
            interaction.guild_id,
            member.id,
            interaction.user.id,
            "timeout",
            reason_str,
            int(td.total_seconds()),
        )
        log_cog = self._get_logging_cog()
        if log_cog:
            await log_cog.log_mod_action(
                interaction.guild_id,
                "Timeout",
                member,
                interaction.user,
                reason_str,
                duration=duration_str,
            )

    # ─────────────────────────────────────────────
    # /mute (role-based)
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="mute", description="Mute a member using the configured mute role."
    )
    @app_commands.describe(member="The member to mute", reason="Reason for the mute")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        allowed, msg = self.guard.can_moderate(interaction.user, member)
        if not allowed:
            await interaction.response.send_message(
                embed=error_embed(msg), ephemeral=True
            )
            return

        mute_role_id = await self.bot.db.get_mute_role(interaction.guild_id)
        if mute_role_id is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "No mute role configured. Use `/setup muterole` to set one."
                ),
                ephemeral=True,
            )
            return

        mute_role = interaction.guild.get_role(mute_role_id)
        if mute_role is None:
            await interaction.response.send_message(
                embed=error_embed("Mute role not found. It may have been deleted."),
                ephemeral=True,
            )
            return

        reason_str = reason or "No reason provided"

        try:
            await member.add_roles(
                mute_role, reason=f"[{interaction.user}] {reason_str}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("I don't have permission to add the mute role."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=moderation_embed("Mute", member, interaction.user, reason_str)
        )
        await self.bot.db.log_mod_action(
            interaction.guild_id, member.id, interaction.user.id, "mute", reason_str
        )

    # ─────────────────────────────────────────────
    # /unmute
    # ─────────────────────────────────────────────

    @app_commands.command(name="unmute", description="Unmute a muted member.")
    @app_commands.describe(member="The member to unmute", reason="Reason for unmute")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def unmute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        mute_role_id = await self.bot.db.get_mute_role(interaction.guild_id)
        if mute_role_id is None:
            await interaction.response.send_message(
                embed=error_embed("No mute role configured."), ephemeral=True
            )
            return

        mute_role = interaction.guild.get_role(mute_role_id)
        if mute_role not in member.roles:
            await interaction.response.send_message(
                embed=error_embed("This member is not muted."), ephemeral=True
            )
            return

        reason_str = reason or "No reason provided"
        await member.remove_roles(
            mute_role, reason=f"[{interaction.user}] {reason_str}"
        )

        await interaction.response.send_message(
            embed=moderation_embed("Unmute", member, interaction.user, reason_str)
        )

    # ─────────────────────────────────────────────
    # /warn
    # ─────────────────────────────────────────────

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        reason_str = reason or "No reason provided"

        warn_id = await self.bot.db.add_warning(
            interaction.guild_id,
            member.id,
            interaction.user.id,
            reason_str,
        )
        warnings = await self.bot.db.get_warnings(interaction.guild_id, member.id)

        embed = moderation_embed(
            "Warning",
            member,
            interaction.user,
            reason_str,
            extra_fields=[
                ("Warning #", str(len(warnings)), True),
                ("Warning ID", str(warn_id), True),
            ],
        )
        await interaction.response.send_message(embed=embed)

        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title=f"⚠️ You were warned in {interaction.guild.name}",
                description=f"**Reason:** {reason_str}\n**Total warnings:** {len(warnings)}",
                color=config.color_warning,
            )
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    # ─────────────────────────────────────────────
    # /warnings
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="warnings", description="View a member's warnings."
    )
    @app_commands.describe(member="The member to check")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        warns = await self.bot.db.get_warnings(interaction.guild_id, member.id)

        if not warns:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{member.mention} has no warnings.",
                    color=config.color_success,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"⚠️ Warnings for {member}",
            description=f"**{len(warns)}** total warning(s)",
            color=config.color_warning,
        )
        for w in warns[:10]:  # Show latest 10
            embed.add_field(
                name=f"#{w['id']} — {w['created_at'][:10]}",
                value=f"**Reason:** {w['reason'] or 'N/A'}\n**By:** <@{w['moderator_id']}>",
                inline=False,
            )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────
    # /clear
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="clear", description="Delete messages in the current channel."
    )
    @app_commands.describe(
        amount="Number of messages to delete (1-100)",
        member="Only delete messages from this member (optional)",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        member: Optional[discord.Member] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        def check(msg: discord.Message) -> bool:
            if member:
                return msg.author == member
            return True

        try:
            deleted = await interaction.channel.purge(limit=amount, check=check)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("I don't have permission to delete messages."),
                ephemeral=True,
            )
            return

        target_str = f" from {member.mention}" if member else ""
        await interaction.followup.send(
            embed=success_embed(
                f"Deleted **{len(deleted)}** message(s){target_str}."
            ),
            ephemeral=True,
        )

    # ─────────────────────────────────────────────
    # /lock
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="lock", description="Lock the current channel (deny @everyone from sending)."
    )
    @app_commands.describe(reason="Reason for locking")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def lock(
        self,
        interaction: discord.Interaction,
        reason: Optional[str] = None,
    ) -> None:
        channel = interaction.channel
        everyone = interaction.guild.default_role

        overwrite = channel.overwrites_for(everyone)
        overwrite.send_messages = False
        await channel.set_permissions(
            everyone,
            overwrite=overwrite,
            reason=f"[{interaction.user}] {reason or 'Channel locked'}",
        )

        await interaction.response.send_message(
            embed=success_embed(
                f"🔒 Channel **{channel.name}** has been locked.\n**Reason:** {reason or 'No reason provided'}"
            )
        )

    # ─────────────────────────────────────────────
    # /unlock
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="unlock", description="Unlock the current channel."
    )
    @app_commands.describe(reason="Reason for unlocking")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def unlock(
        self,
        interaction: discord.Interaction,
        reason: Optional[str] = None,
    ) -> None:
        channel = interaction.channel
        everyone = interaction.guild.default_role

        overwrite = channel.overwrites_for(everyone)
        overwrite.send_messages = None  # Reset to default
        await channel.set_permissions(
            everyone,
            overwrite=overwrite,
            reason=f"[{interaction.user}] {reason or 'Channel unlocked'}",
        )

        await interaction.response.send_message(
            embed=success_embed(
                f"🔓 Channel **{channel.name}** has been unlocked."
            )
        )

    # ─────────────────────────────────────────────
    # /slowmode
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="slowmode", description="Set slowmode in the current channel."
    )
    @app_commands.describe(
        seconds="Slowmode delay in seconds (0 to disable, max 21600)"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
    ) -> None:
        await interaction.channel.edit(slowmode_delay=seconds)

        if seconds == 0:
            msg = f"Slowmode disabled in **{interaction.channel.name}**."
        else:
            msg = f"Slowmode set to **{seconds}s** in **{interaction.channel.name}**."

        await interaction.response.send_message(embed=success_embed(msg))

    # ─────────────────────────────────────────────
    # /history
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="history", description="View moderation history for a member."
    )
    @app_commands.describe(member="The member to check")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def history(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        actions = await self.bot.db.get_user_history(interaction.guild_id, member.id)

        if not actions:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{member.mention} has no moderation history.",
                    color=config.color_success,
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📋 Mod History for {member}",
            description=f"**{len(actions)}** action(s) on record",
            color=config.color_moderation,
        )
        for a in actions[:10]:
            embed.add_field(
                name=f"{a['action'].upper()} — {a['created_at'][:10]}",
                value=f"**Reason:** {a['reason'] or 'N/A'}\n**By:** <@{a['moderator_id']}>",
                inline=False,
            )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    await bot.add_cog(Moderation(bot))

"""
Utilities Cog - cogs/utilities.py
General utility commands: setup, status, help, server info, etc.
"""

import logging
import platform
import sys
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from utils.embeds import success_embed, error_embed, info_embed

logger = logging.getLogger(__name__)


class Utilities(commands.Cog, name="Utilities"):
    """General utility commands for bot setup and information."""

    def __init__(self, bot) -> None:
        self.bot = bot

    # ─────────────────────────────────────────────
    # /help
    # ─────────────────────────────────────────────

    @app_commands.command(name="help", description="Show all available commands.")
    @app_commands.guild_only()
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title=f"🛡️ {config.bot_name} Bot — Command Reference",
            description="Production-grade moderation and anti-nuke protection.",
            color=config.color_info,
        )

        embed.add_field(
            name="🔨 Moderation",
            value=(
                "`/ban` `/kick` `/timeout` `/mute` `/unmute`\n"
                "`/warn` `/warnings` `/history`\n"
                "`/clear` `/lock` `/unlock` `/slowmode`"
            ),
            inline=False,
        )
        embed.add_field(
            name="📋 Whitelist",
            value="`/whitelist add` `/whitelist remove` `/whitelist list` `/whitelist check`",
            inline=False,
        )
        embed.add_field(
            name="⚙️ Setup",
            value="`/setup logchannel` `/setup muterole` `/setup antinuke` `/setup spam`",
            inline=False,
        )
        embed.add_field(
            name="ℹ️ Info",
            value="`/help` `/ping` `/botinfo` `/serverinfo` `/userinfo`",
            inline=False,
        )
        embed.set_footer(
            text=f"Guardian Bot v{config.version} | Use /setup to configure the bot"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ─────────────────────────────────────────────
    # /ping
    # ─────────────────────────────────────────────

    @app_commands.command(name="ping", description="Check the bot's latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        color = (
            config.color_success
            if latency_ms < 100
            else config.color_warning
            if latency_ms < 200
            else config.color_error
        )
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"**WebSocket Latency:** {latency_ms}ms",
            color=color,
        )
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────
    # /botinfo
    # ─────────────────────────────────────────────

    @app_commands.command(name="botinfo", description="View information about the bot.")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title=f"🤖 {config.bot_name} Bot Info",
            color=config.color_info,
        )
        embed.add_field(name="Version", value=config.version, inline=True)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(
            name="Total Members",
            value=str(sum(g.member_count or 0 for g in self.bot.guilds)),
            inline=True,
        )
        embed.add_field(
            name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True
        )
        embed.add_field(
            name="Python",
            value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            inline=True,
        )
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────
    # /serverinfo
    # ─────────────────────────────────────────────

    @app_commands.command(name="serverinfo", description="View server information.")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        embed = discord.Embed(
            title=f"🏠 {guild.name}",
            description=guild.description or "No description.",
            color=config.color_info,
        )
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(
            name="Verification Level", value=str(guild.verification_level), inline=True
        )
        embed.add_field(
            name="Created",
            value=discord.utils.format_dt(guild.created_at, style="R"),
            inline=True,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Guild ID: {guild.id}")
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────
    # /userinfo
    # ─────────────────────────────────────────────

    @app_commands.command(
        name="userinfo", description="View information about a user."
    )
    @app_commands.describe(member="The member to view (defaults to yourself)")
    @app_commands.guild_only()
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        member = member or interaction.user
        embed = discord.Embed(
            title=f"👤 {member}",
            color=member.color if member.color != discord.Color.default() else config.color_info,
        )
        embed.add_field(
            name="Joined Server",
            value=discord.utils.format_dt(member.joined_at, style="R")
            if member.joined_at
            else "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(member.created_at, style="R"),
            inline=True,
        )
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Bot?", value="✅" if member.bot else "❌", inline=True)

        roles = [r.mention for r in member.roles[1:]]  # Skip @everyone
        if roles:
            embed.add_field(
                name=f"Roles ({len(roles)})",
                value=" ".join(roles[:10]) + (" ..." if len(roles) > 10 else ""),
                inline=False,
            )

        is_wl = await self.bot.db.is_whitelisted(interaction.guild_id, member.id)
        embed.add_field(
            name="Whitelisted",
            value="✅ Yes" if is_wl else "❌ No",
            inline=True,
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"User ID: {member.id}")
        await interaction.response.send_message(embed=embed)

    # ─────────────────────────────────────────────
    # Setup commands group
    # ─────────────────────────────────────────────

    setup_group = app_commands.Group(
        name="setup",
        description="Configure bot settings for this server.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )

    @setup_group.command(
        name="logchannel", description="Set the channel for bot logs."
    )
    @app_commands.describe(channel="The channel to send logs to")
    async def setup_logchannel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        # Verify bot can send to the channel
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                embed=error_embed(
                    f"I don't have permission to send messages in {channel.mention}."
                ),
                ephemeral=True,
            )
            return

        await self.bot.db.set_log_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            embed=success_embed(
                f"✅ Log channel set to {channel.mention}.\n"
                "All moderation actions, anti-nuke alerts, and spam events will be logged there."
            )
        )

    @setup_group.command(
        name="muterole", description="Set the role used for muting members."
    )
    @app_commands.describe(role="The role to use as the mute role")
    async def setup_muterole(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ) -> None:
        await self.bot.db.set_mute_role(interaction.guild_id, role.id)
        await interaction.response.send_message(
            embed=success_embed(
                f"✅ Mute role set to {role.mention}.\n"
                "Use `/mute @member` to mute members with this role."
            )
        )

    @setup_group.command(
        name="antinuke", description="Enable or disable anti-nuke protection."
    )
    @app_commands.describe(enabled="Enable or disable anti-nuke")
    async def setup_antinuke(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ) -> None:
        await self.bot.db.ensure_guild(interaction.guild_id)
        await self.bot.db.execute(
            "UPDATE guild_settings SET antinuke_enabled = ? WHERE guild_id = ?",
            (int(enabled), interaction.guild_id),
        )
        status = "✅ enabled" if enabled else "❌ disabled"
        await interaction.response.send_message(
            embed=success_embed(f"Anti-nuke protection has been **{status}**.")
        )

    @setup_group.command(
        name="spam", description="Enable or disable spam protection."
    )
    @app_commands.describe(enabled="Enable or disable spam detection")
    async def setup_spam(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ) -> None:
        await self.bot.db.ensure_guild(interaction.guild_id)
        await self.bot.db.execute(
            "UPDATE guild_settings SET spam_enabled = ? WHERE guild_id = ?",
            (int(enabled), interaction.guild_id),
        )
        status = "✅ enabled" if enabled else "❌ disabled"
        await interaction.response.send_message(
            embed=success_embed(f"Spam detection has been **{status}**.")
        )

    @setup_group.command(
        name="status", description="View current bot configuration for this server."
    )
    async def setup_status(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.ensure_guild(interaction.guild_id)

        log_ch = (
            f"<#{settings['log_channel_id']}>"
            if settings.get("log_channel_id")
            else "Not set"
        )
        mute_role = (
            f"<@&{settings['mute_role_id']}>"
            if settings.get("mute_role_id")
            else "Not set"
        )
        antinuke = "✅ Enabled" if settings.get("antinuke_enabled", 1) else "❌ Disabled"
        spam = "✅ Enabled" if settings.get("spam_enabled", 1) else "❌ Disabled"

        wl_entries = await self.bot.db.get_whitelist(interaction.guild_id)

        embed = discord.Embed(
            title="⚙️ Bot Configuration",
            color=config.color_info,
        )
        embed.add_field(name="Log Channel", value=log_ch, inline=True)
        embed.add_field(name="Mute Role", value=mute_role, inline=True)
        embed.add_field(name="Anti-Nuke", value=antinuke, inline=True)
        embed.add_field(name="Spam Detection", value=spam, inline=True)
        embed.add_field(
            name="Whitelisted Users", value=str(len(wl_entries)), inline=True
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot) -> None:
    cog = Utilities(bot)
    bot.tree.add_command(cog.setup_group)
    await bot.add_cog(cog)

"""
Whitelist Cog - cogs/whitelist.py
Manage the anti-nuke whitelist per guild.
Whitelisted users bypass anti-nuke protection but are still monitored for spam.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from utils.embeds import success_embed, error_embed, info_embed
from utils.helpers import get_or_fetch_user

logger = logging.getLogger(__name__)


class Whitelist(commands.Cog, name="Whitelist"):
    """
    Anti-nuke whitelist management.
    Allows trusted users to perform admin actions without triggering anti-nuke.
    """

    def __init__(self, bot) -> None:
        self.bot = bot

    # ─────────────────────────────────────────────
    # Whitelist command group
    # ─────────────────────────────────────────────

    whitelist_group = app_commands.Group(
        name="whitelist",
        description="Manage the anti-nuke whitelist.",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )

    @whitelist_group.command(
        name="add", description="Add a user to the anti-nuke whitelist."
    )
    @app_commands.describe(user="The user to whitelist")
    async def whitelist_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        # Only guild owner or admins can manage whitelist
        if (
            interaction.user.id != interaction.guild.owner_id
            and not interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                embed=error_embed("Only the server owner or admins can manage the whitelist."),
                ephemeral=True,
            )
            return

        # Cannot whitelist the bot itself
        if user.bot:
            await interaction.response.send_message(
                embed=error_embed("You cannot whitelist a bot."),
                ephemeral=True,
            )
            return

        added = await self.bot.db.add_whitelist(
            interaction.guild_id, user.id, interaction.user.id
        )

        if not added:
            await interaction.response.send_message(
                embed=error_embed(f"{user.mention} is already whitelisted."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                f"✅ {user.mention} has been added to the anti-nuke whitelist.\n"
                "They can now perform admin actions without triggering anti-nuke protection."
            )
        )

        # Log whitelist change
        log_cog = self.bot.get_cog("Logging")
        if log_cog:
            await log_cog.log_whitelist_change(
                interaction.guild_id,
                user.id,
                interaction.user.id,
                "Added to whitelist",
            )

    @whitelist_group.command(
        name="remove", description="Remove a user from the anti-nuke whitelist."
    )
    @app_commands.describe(user="The user to remove from the whitelist")
    async def whitelist_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        if (
            interaction.user.id != interaction.guild.owner_id
            and not interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                embed=error_embed("Only the server owner or admins can manage the whitelist."),
                ephemeral=True,
            )
            return

        removed = await self.bot.db.remove_whitelist(interaction.guild_id, user.id)

        if not removed:
            await interaction.response.send_message(
                embed=error_embed(f"{user.mention} is not in the whitelist."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=success_embed(
                f"✅ {user.mention} has been removed from the anti-nuke whitelist."
            )
        )

        log_cog = self.bot.get_cog("Logging")
        if log_cog:
            await log_cog.log_whitelist_change(
                interaction.guild_id,
                user.id,
                interaction.user.id,
                "Removed from whitelist",
            )

    @whitelist_group.command(
        name="list", description="View all whitelisted users."
    )
    async def whitelist_list(
        self,
        interaction: discord.Interaction,
    ) -> None:
        entries = await self.bot.db.get_whitelist(interaction.guild_id)

        if not entries:
            await interaction.response.send_message(
                embed=info_embed(
                    "No users are currently whitelisted.\nUse `/whitelist add @user` to add someone."
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📋 Anti-Nuke Whitelist",
            description=f"**{len(entries)}** whitelisted user(s)",
            color=config.color_info,
        )

        for entry in entries:
            user = self.bot.get_user(entry["user_id"])
            user_str = (
                f"{user.mention} (`{entry['user_id']}`)"
                if user
                else f"Unknown User (`{entry['user_id']}`)"
            )
            added_by = self.bot.get_user(entry["added_by"])
            added_by_str = (
                f"{added_by.mention}" if added_by else f"<@{entry['added_by']}>"
            )
            embed.add_field(
                name=user_str,
                value=f"Added by {added_by_str} on {entry['added_at'][:10]}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @whitelist_group.command(
        name="check", description="Check if a user is whitelisted."
    )
    @app_commands.describe(user="The user to check")
    async def whitelist_check(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        is_wl = await self.bot.db.is_whitelisted(interaction.guild_id, user.id)
        status = "✅ whitelisted" if is_wl else "❌ not whitelisted"

        await interaction.response.send_message(
            embed=info_embed(
                f"{user.mention} is **{status}** in this server."
            ),
            ephemeral=True,
        )


async def setup(bot) -> None:
    cog = Whitelist(bot)
    bot.tree.add_command(cog.whitelist_group)
    await bot.add_cog(cog)

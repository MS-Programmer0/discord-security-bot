"""
Core Bot - core/bot.py
Main bot class that ties everything together.
"""

import logging
import traceback
from typing import Optional

import discord
from discord.ext import commands

from config import config
from database.database import Database

logger = logging.getLogger(__name__)


class GuardianBot(commands.Bot):
    """
    Production-grade Discord moderation and anti-nuke bot.

    Inherits from commands.Bot with added:
    - Async database access
    - Security manager
    - Rate limiter
    - Centralized error handling
    """

    def __init__(self) -> None:
        intents = discord.Intents.all()

        super().__init__(
            command_prefix=commands.when_mentioned,  # Prefixless slash commands only
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )

        self.config = config
        self.db: Database = Database(config.db_path)

        # Lazy-loaded managers (set after cogs load)
        self.security_manager = None
        self.rate_limiter = None

    # ─────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────

    async def setup_hook(self) -> None:
        """Called before the bot starts. Load cogs and sync commands."""
        await self.db.connect()
        logger.info("Database connected.")

        # Load all cogs
        for cog_path in self.config.cogs:
            try:
                await self.load_extension(cog_path)
                logger.info(f"Loaded cog: {cog_path}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog_path}: {e}")
                traceback.print_exc()

        # Sync slash commands globally
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash command(s).")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def close(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down Guardian Bot...")
        await self.db.close()
        await super().close()

    # ─────────────────────────────────────────────
    # Events
    # ─────────────────────────────────────────────

    async def on_ready(self) -> None:
        logger.info(
            f"Guardian Bot ready! Logged in as {self.user} (ID: {self.user.id})"
        )
        logger.info(f"Serving {len(self.guilds)} guild(s).")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servers | /help",
            )
        )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Initialize guild settings when bot joins."""
        await self.db.ensure_guild(guild.id)
        logger.info(f"Joined guild: {guild.name} ({guild.id})")

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        logger.info(f"Removed from guild: {guild.name} ({guild.id})")

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        """Global slash command error handler."""
        from utils.embeds import error_embed

        if isinstance(error, discord.app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=error_embed("You don't have permission to use this command."),
                ephemeral=True,
            )
        elif isinstance(error, discord.app_commands.BotMissingPermissions):
            await interaction.response.send_message(
                embed=error_embed(
                    f"I'm missing permissions: {', '.join(error.missing_permissions)}"
                ),
                ephemeral=True,
            )
        elif isinstance(error, discord.app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                embed=error_embed(
                    f"Command on cooldown. Try again in **{error.retry_after:.1f}s**."
                ),
                ephemeral=True,
            )
        else:
            logger.error(
                f"Unhandled app command error in {interaction.command}: {error}",
                exc_info=True,
            )
            try:
                await interaction.response.send_message(
                    embed=error_embed("An unexpected error occurred."),
                    ephemeral=True,
                )
            except Exception:
                pass

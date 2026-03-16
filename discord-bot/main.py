"""
Production-Grade Discord Moderation & Anti-Nuke Bot
Entry Point - main.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Initialize and run the bot."""
    # Import here to allow .env to load first
    from core.bot import GuardianBot

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("DISCORD_TOKEN not found in environment variables!")
        sys.exit(1)

    bot = GuardianBot()

    try:
        logger.info("Starting Guardian Bot...")
        async with bot:
            await bot.start(token)
    except discord.LoginFailure:
        logger.critical("Invalid Discord token provided!")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

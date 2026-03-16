"""
Configuration - config.py
Central configuration for the bot using environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AntiNukeConfig:
    """Thresholds for anti-nuke detection."""
    channel_delete_limit: int = 3
    channel_delete_window: int = 10  # seconds

    channel_create_limit: int = 5
    channel_create_window: int = 10

    role_delete_limit: int = 3
    role_delete_window: int = 10

    role_create_limit: int = 5
    role_create_window: int = 10

    ban_limit: int = 5
    ban_window: int = 10

    kick_limit: int = 5
    kick_window: int = 10

    webhook_create_limit: int = 3
    webhook_create_window: int = 10

    mass_mention_limit: int = 10
    mass_mention_window: int = 5


@dataclass
class SpamConfig:
    """Spam detection thresholds."""
    warn_message_count: int = 5
    warn_message_window: int = 5  # seconds

    mute_message_count: int = 10
    mute_message_window: int = 5

    kick_message_count: int = 20
    kick_message_window: int = 5

    mention_limit: int = 5
    mention_window: int = 10

    link_limit: int = 3
    link_window: int = 10

    emoji_limit: int = 10
    emoji_window: int = 10

    duplicate_limit: int = 5
    duplicate_window: int = 10

    mute_duration: int = 300  # seconds (5 minutes)


@dataclass
class BotConfig:
    """Main bot configuration."""
    # Bot identity
    bot_name: str = "Guardian"
    version: str = "1.0.0"

    # Embed colors
    color_success: int = 0x2ECC71
    color_error: int = 0xE74C3C
    color_warning: int = 0xF39C12
    color_info: int = 0x3498DB
    color_moderation: int = 0x9B59B6
    color_antinuke: int = 0xFF0000

    # Database
    db_path: str = os.getenv("DB_PATH", "guardian.db")

    # Owner
    owner_id: Optional[int] = int(os.getenv("OWNER_ID", "0")) or None

    # Anti-nuke
    antinuke: AntiNukeConfig = field(default_factory=AntiNukeConfig)

    # Spam
    spam: SpamConfig = field(default_factory=SpamConfig)

    # Cog paths
    cogs: list = field(default_factory=lambda: [
        "cogs.moderation",
        "cogs.antinuke",
        "cogs.whitelist",
        "cogs.spam_protection",
        "cogs.logging_system",
        "cogs.utilities",
    ])


# Singleton config instance
config = BotConfig()

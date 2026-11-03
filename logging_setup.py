"""File logging for moderation actions. Never log tokens or API keys."""

from __future__ import annotations

import logging
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "moderation.log"
LOGGER_NAME = "moderator"


def setup_logging() -> logging.Logger:
    """Create `logs/moderation.log` and return the action logger."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(isinstance(handler, logging.FileHandler) for handler in logger.handlers):
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(file_handler)

        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(console)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger


def log_action(
    *,
    guild_id: int | None,
    channel_id: int | None,
    user_id: int | None,
    action: str,
    reason: str,
    level: int = logging.INFO,
) -> None:
    """Write one structured action line. Do not pass secrets into `reason`."""

    logger = logging.getLogger(LOGGER_NAME)
    logger.log(
        level,
        "guild=%s channel=%s user=%s action=%s reason=%s",
        guild_id if guild_id is not None else "-",
        channel_id if channel_id is not None else "-",
        user_id if user_id is not None else "-",
        action,
        reason.replace("\n", " ").strip(),
    )

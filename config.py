"""Load and validate settings from the environment."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

logger = logging.getLogger("moderator")

DEFAULT_MUTE_MINUTES = 10
DEFAULT_SPAM_WINDOW_SECONDS = 10
DEFAULT_SPAM_MAX_MESSAGES = 5
DEFAULT_SPAM_TIMEOUT_MINUTES = 10
DEFAULT_MODERATION_MODEL = "omni-moderation-latest"


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Secrets stay in env vars, never in code."""

    discord_token: str
    openai_api_key: str
    log_channel_id: int | None
    mute_minutes: int
    moderation_model: str
    bypass_role_id: int | None
    spam_window_seconds: int
    spam_max_messages: int
    spam_timeout_minutes: int
    roles: tuple[tuple[int, str], ...]


def _parse_optional_id(raw: str, name: str) -> int | None:
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        logger.warning("Invalid %s=%r, ignoring", name, value)
        return None
    if parsed <= 0:
        logger.warning("Invalid %s=%r, ignoring", name, value)
        return None
    return parsed


def _parse_positive_int(raw: str, name: str, default: int) -> int:
    value = raw.strip()
    if not value:
        return default
    try:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError
        return parsed
    except ValueError:
        logger.warning("Invalid %s=%r, using default %s", name, value, default)
        return default


def _load_roles() -> tuple[tuple[int, str], ...]:
    roles: list[tuple[int, str]] = []
    seen: set[int] = set()
    for index in (1, 2, 3):
        role_id = _parse_optional_id(os.getenv(f"ROLE_ID_{index}", ""), f"ROLE_ID_{index}")
        if role_id is None:
            continue
        if role_id in seen:
            logger.warning("Duplicate ROLE_ID_%s=%s, skipping", index, role_id)
            continue
        label = os.getenv(f"ROLE_LABEL_{index}", "").strip() or f"Role {index}"
        roles.append((role_id, label[:80]))
        seen.add(role_id)
    return tuple(roles)


def load_settings() -> Settings:
    """Read `.env` and return settings. Empty DISCORD_TOKEN stops the process."""

    load_dotenv()

    discord_token = os.getenv("DISCORD_TOKEN", "").strip()
    if not discord_token:
        raise SystemExit(
            "DISCORD_TOKEN is empty. Copy .env.example to .env and paste the bot token."
        )

    return Settings(
        discord_token=discord_token,
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        log_channel_id=_parse_optional_id(os.getenv("LOG_CHANNEL_ID", ""), "LOG_CHANNEL_ID"),
        mute_minutes=_parse_positive_int(
            os.getenv("MUTE_MINUTES", ""), "MUTE_MINUTES", DEFAULT_MUTE_MINUTES
        ),
        moderation_model=os.getenv("MODERATION_MODEL", "").strip() or DEFAULT_MODERATION_MODEL,
        bypass_role_id=_parse_optional_id(os.getenv("BYPASS_ROLE_ID", ""), "BYPASS_ROLE_ID"),
        spam_window_seconds=_parse_positive_int(
            os.getenv("SPAM_WINDOW_SECONDS", ""),
            "SPAM_WINDOW_SECONDS",
            DEFAULT_SPAM_WINDOW_SECONDS,
        ),
        spam_max_messages=_parse_positive_int(
            os.getenv("SPAM_MAX_MESSAGES", ""),
            "SPAM_MAX_MESSAGES",
            DEFAULT_SPAM_MAX_MESSAGES,
        ),
        spam_timeout_minutes=_parse_positive_int(
            os.getenv("SPAM_TIMEOUT_MINUTES", ""),
            "SPAM_TIMEOUT_MINUTES",
            DEFAULT_SPAM_TIMEOUT_MINUTES,
        ),
        roles=_load_roles(),
    )

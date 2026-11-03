"""OpenAI Moderation API wrapper with a safe offline fallback."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from openai import APITimeoutError, AsyncOpenAI, RateLimitError

from logging_setup import log_action

logger = logging.getLogger("moderator")

WATCHED_CATEGORIES = (
    "hate",
    "hate/threatening",
    "harassment",
    "harassment/threatening",
    "violence",
    "violence/graphic",
    "sexual",
    "sexual/minors",
    "self-harm",
    "self-harm/intent",
    "self-harm/instructions",
)

API_TIMEOUT_SECONDS = 15.0
RETRY_SLEEP_SECONDS = 2.0


@dataclass(frozen=True)
class ModerationResult:
    """Outcome of a text check. `used_api=False` means fallback or an API error."""

    flagged: bool
    categories: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""
    used_api: bool = False


def _category_flags(result: object) -> dict[str, bool]:
    categories = getattr(result, "categories", None)
    if categories is None:
        return {}
    if hasattr(categories, "model_dump"):
        dumped = categories.model_dump(by_alias=True)
        return {str(key): bool(value) for key, value in dumped.items()}
    return {}


class ModerationChecker:
    """Calls omni-moderation when a key is set; otherwise treats text as clean."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client: AsyncOpenAI | None = None
        self._fallback_warned = False
        if api_key:
            self._client = AsyncOpenAI(api_key=api_key, timeout=API_TIMEOUT_SECONDS)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _warn_fallback(self) -> None:
        # RU: Без ключа не падаем — считаем сообщение чистым.
        # EN: Missing API key must not crash; treat the message as clean.
        if self._fallback_warned:
            return
        self._fallback_warned = True
        logger.warning(
            "OPENAI_API_KEY is empty; moderation API disabled, all messages treated as clean"
        )
        log_action(
            guild_id=None,
            channel_id=None,
            user_id=None,
            action="fallback",
            reason="OPENAI_API_KEY empty, toxicity checks skipped",
            level=logging.WARNING,
        )

    async def check_text(self, text: str) -> ModerationResult:
        """Return whether `text` is flagged. API failures do not punish the user."""

        if self._client is None:
            self._warn_fallback()
            return ModerationResult(flagged=False, used_api=False)

        last_error = "unknown error"
        for attempt in range(2):
            try:
                response = await self._client.moderations.create(
                    input=text,
                    model=self._model,
                )
                result = response.results[0]
                flags = _category_flags(result)
                hit_categories = tuple(
                    name for name in WATCHED_CATEGORIES if flags.get(name)
                )
                flagged = bool(getattr(result, "flagged", False) and hit_categories)
                reason = (
                    "toxicity: " + ", ".join(hit_categories) if flagged else "clean"
                )
                return ModerationResult(
                    flagged=flagged,
                    categories=hit_categories,
                    reason=reason,
                    used_api=True,
                )
            except RateLimitError:
                last_error = "rate limit"
            except APITimeoutError:
                last_error = "timeout"
            except Exception as exc:  # noqa: BLE001 — keep the bot running
                last_error = type(exc).__name__
                break

            if attempt == 0:
                await asyncio.sleep(RETRY_SLEEP_SECONDS)

        logger.error("Moderation API failed (%s); message left unflagged", last_error)
        log_action(
            guild_id=None,
            channel_id=None,
            user_id=None,
            action="api_error",
            reason=f"moderation API {last_error}, message not punished",
            level=logging.ERROR,
        )
        return ModerationResult(flagged=False, used_api=False, reason=last_error)

"""Cheap in-memory spam heuristics. No database."""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass

INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)
REPEAT_LIMIT = 3


@dataclass(frozen=True)
class SpamHit:
    flagged: bool
    reason: str = ""


def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())


class SpamTracker:
    """Per-guild, per-user sliding window of recent messages."""

    def __init__(self, window_seconds: int, max_messages: int) -> None:
        self.window_seconds = window_seconds
        self.max_messages = max_messages
        self._history: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(deque)

    def _prune(self, history: deque[tuple[float, str]], now: float) -> None:
        cutoff = now - self.window_seconds
        while history and history[0][0] < cutoff:
            history.popleft()

    def check(
        self,
        *,
        guild_id: int,
        user_id: int,
        content: str,
        mention_count: int,
        mention_everyone: bool,
    ) -> SpamHit:
        now = time.monotonic()
        history = self._history[(guild_id, user_id)]
        self._prune(history, now)
        normalized = normalize_text(content)
        history.append((now, normalized))

        if INVITE_RE.search(content):
            return SpamHit(True, "spam: discord invite")
        if mention_everyone:
            return SpamHit(True, "spam: @everyone/@here")
        if mention_count >= 5:
            return SpamHit(True, "spam: too many mentions")
        if len(history) > self.max_messages:
            return SpamHit(True, "spam: too many messages")
        repeats = sum(1 for _, text in history if text == normalized)
        if repeats >= REPEAT_LIMIT:
            return SpamHit(True, "spam: repeated text")
        return SpamHit(False)

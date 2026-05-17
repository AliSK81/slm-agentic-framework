"""Thinking-token budget for models that emit reasoning streams."""

from __future__ import annotations


class ThinkingBudget:
    """Tracks consumed thinking tokens against a hard limit."""

    def __init__(self, limit: int = 2048) -> None:
        self._limit = limit
        self._used = 0
        self._buffer: list[str] = []

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return max(self._limit - self._used, 0)

    def feed(self, token: str) -> bool:
        """Record one token; return False when budget is exhausted."""
        cost = max(len(token) // 4, 1)
        if self._used + cost > self._limit:
            return False
        self._used += cost
        self._buffer.append(token)
        return True

    def reuse_context(self) -> str:
        """Return accumulated thinking text for corrective prompts."""
        return "".join(self._buffer)

    def reset(self) -> None:
        """Clear buffer and usage."""
        self._used = 0
        self._buffer.clear()

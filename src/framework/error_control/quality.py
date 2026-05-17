"""Output quality gate before accepting SLM decisions."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel

from framework.memory.stores import DecisionEntry


class QualityResult(BaseModel):
    """Result of quality gate evaluation."""

    passed: bool
    failure_mode: Literal["empty_response", "unparseable", "loop"] | None = None


class QualityGate:
    """Deterministic checks on raw and parsed SLM output."""

    def __init__(self, loop_threshold: int = 3, window: int = 5) -> None:
        self._loop_threshold = loop_threshold
        self._window = window

    @staticmethod
    def _decision_hash(entry: DecisionEntry) -> str:
        payload = json.dumps(entry.payload, sort_keys=True, default=str)
        digest = f"{entry.kind}:{payload}"
        return hashlib.sha256(digest.encode()).hexdigest()

    def _loop_detected(self, recent_decisions: list[DecisionEntry]) -> bool:
        window = recent_decisions[-self._window :]
        counts: dict[str, int] = {}
        for entry in window:
            key = self._decision_hash(entry)
            counts[key] = counts.get(key, 0) + 1
            if counts[key] >= self._loop_threshold:
                return True
        return False

    def check(
        self,
        raw_text: str,
        parsed: BaseModel | None,
        recent_decisions: list[DecisionEntry],
    ) -> QualityResult:
        """FAIL on empty, unparseable, or repeated decision loop."""
        if not raw_text or not raw_text.strip():
            return QualityResult(passed=False, failure_mode="empty_response")
        if parsed is None:
            return QualityResult(passed=False, failure_mode="unparseable")
        if self._loop_detected(recent_decisions):
            return QualityResult(passed=False, failure_mode="loop")
        return QualityResult(passed=True)

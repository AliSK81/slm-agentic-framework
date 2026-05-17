"""Step and retry budget helpers."""

from __future__ import annotations


class StepBudgetLimiter:
    """Tracks session step and per-cycle retry budgets."""

    def __init__(self, max_steps: int, max_retries: int) -> None:
        self.max_steps = max_steps
        self.max_retries = max_retries

    def check_steps(self, current: int) -> bool:
        """Return True when another step is allowed."""
        return current < self.max_steps

    def check_retries(self, current: int) -> bool:
        """Return True when another retry is allowed."""
        return current < self.max_retries

    def remaining(self, current: int) -> dict[str, int]:
        """Remaining step and retry budget."""
        return {
            "steps": max(self.max_steps - current, 0),
            "retries": max(self.max_retries - current, 0),
        }

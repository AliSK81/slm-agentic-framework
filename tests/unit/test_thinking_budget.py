"""Unit tests for ThinkingBudget (phase 28)."""

from __future__ import annotations

from framework.error_control.thinking import ThinkingBudget


def test_thinking_budget_aborts_at_limit() -> None:
    """feed returns False once the token budget is exhausted."""
    budget = ThinkingBudget(limit=10)
    assert budget.feed("x" * 40) is True
    assert budget.feed("y" * 40) is False
    assert budget.used >= 10


def test_thinking_budget_reuse_context_returns_prior() -> None:
    """reuse_context returns accumulated thinking text before reset."""
    budget = ThinkingBudget(limit=100)
    budget.feed("alpha ")
    budget.feed("beta")
    assert budget.reuse_context() == "alpha beta"
    budget.reset()
    assert budget.reuse_context() == ""
    assert budget.used == 0

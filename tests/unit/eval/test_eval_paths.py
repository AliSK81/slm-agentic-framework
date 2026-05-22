"""Evaluation path helper tests."""

from __future__ import annotations

from eval.paths import safe_task_slug


def test_safe_task_slug_replaces_slashes() -> None:
    """HumanEval ids with slashes become flat filenames."""
    assert safe_task_slug("HumanEval/124") == "HumanEval_124"


def test_safe_task_slug_handles_empty() -> None:
    """Empty ids fall back to a default slug."""
    assert safe_task_slug("   ") == "task"

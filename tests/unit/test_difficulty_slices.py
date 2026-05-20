"""Unit tests for HumanEval difficulty labels and hard slice."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from eval.datasets._sample import sample_stratified
from eval.datasets.humaneval_adapter import (
    HumanEvalTask,
    _curated_hard_ids,
    difficulty_of,
    load_humaneval,
)


def _task(
    task_id: str,
    *,
    prompt: str = "def f():\n    pass\n",
    test_code: str = "def check(candidate):\n    assert True\n",
) -> HumanEvalTask:
    return HumanEvalTask(
        task_id=task_id,
        prompt=prompt,
        test_code=test_code,
        entry_point="f",
    )


def test_difficulty_is_deterministic_for_fixed_task() -> None:
    """Same task payload always receives the same difficulty label."""
    task = _task(
        "HumanEval/99",
        prompt="\n".join(f"line {index}" for index in range(14)),
        test_code="\n".join(f"    assert x == {index}" for index in range(8)),
    )
    assert difficulty_of(task) == difficulty_of(task)


def test_hard_slice_contains_only_hard_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """difficulty='hard' filter returns only hard-labeled tasks."""
    rows = [
        _task("HumanEval/0", prompt="def f():\n    pass\n"),
        _task(
            "HumanEval/1",
            prompt="\n".join(f"line {index}" for index in range(14)),
            test_code="\n".join(f"    assert x == {index}" for index in range(8)),
        ),
    ]
    monkeypatch.setattr(
        "eval.datasets.humaneval_adapter._load_humaneval_rows",
        lambda: rows,
    )

    sampled = load_humaneval(n=10, seed=42, difficulty="hard")

    assert sampled
    assert all(difficulty_of(task) == "hard" for task in sampled)


def test_curated_hard_ids_override_heuristic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Curated ids are hard even when heuristics would label them easy."""
    curated_path = tmp_path / "humaneval_hard_ids.txt"
    curated_path.write_text("HumanEval/0\n", encoding="utf-8")
    monkeypatch.setattr(
        "eval.datasets.humaneval_adapter._CURATED_HARD_IDS_PATH",
        curated_path,
    )
    _curated_hard_ids.cache_clear()

    easy_task = _task("HumanEval/0", prompt="def f():\n    pass\n")
    assert difficulty_of(easy_task) == "hard"


def test_stratified_default_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy hash-based stratified sampling is unchanged when difficulty is None."""
    rows = [
        HumanEvalTask(
            task_id=f"HumanEval/{index}",
            prompt="def f(): pass",
            test_code="def check(c): pass",
            entry_point="f",
        )
        for index in range(100)
    ]
    monkeypatch.setattr(
        "eval.datasets.humaneval_adapter._load_humaneval_rows",
        lambda: rows,
    )

    split = {"easy": 2, "medium": 2, "hard": 1}
    expected = sample_stratified(rows, split, seed=42, key_fn=lambda task: task.task_id)
    sampled = load_humaneval(n=5, seed=42, difficulty_split=split)

    assert [task.task_id for task in sampled] == [task.task_id for task in expected]

"""Unit tests for HumanEval difficulty labels and hard slice."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

from eval.config import load_eval_config
from eval.datasets._curated_ids import load_curated_ids
from eval.datasets._sample import sample_stratified
from eval.datasets.humaneval_adapter import (
    HumanEvalTask,
    _CURATED_HARD_IDS_PATH,
    _curated_hard_ids,
    difficulty_of,
    load_humaneval,
    load_humaneval_curated_hard,
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
    load_curated_ids.cache_clear()

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


def test_difficulty_module_shared_by_humaneval_and_mbpp() -> None:
    """HumanEval and MBPP adapters delegate to eval.datasets._difficulty."""
    humaneval_mod = importlib.import_module("eval.datasets.humaneval_adapter")
    mbpp_mod = importlib.import_module("eval.datasets.mbpp_adapter")
    difficulty_mod = importlib.import_module("eval.datasets._difficulty")

    assert humaneval_mod._difficulty_of is difficulty_mod.difficulty_of
    assert mbpp_mod._difficulty_of is difficulty_mod.difficulty_of


def test_hard_slice_size_at_least_30() -> None:
    """Frozen curated hard slice lists at least 30 HumanEval ids."""
    ids = [
        line.strip()
        for line in _CURATED_HARD_IDS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert len(ids) >= 30


def test_slice_is_frozen_and_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same seed and n yield the same task ids across two curated loads."""
    _curated_hard_ids.cache_clear()
    load_curated_ids.cache_clear()
    curated_ids = sorted(load_curated_ids(_CURATED_HARD_IDS_PATH))
    rows = [
        HumanEvalTask(
            task_id=task_id,
            prompt="def f(): pass",
            test_code="def check(c): pass",
            entry_point="f",
        )
        for task_id in curated_ids
    ]
    def _by_ids(task_ids: list[str]) -> list[HumanEvalTask]:
        lookup = {task.task_id: task for task in rows}
        return [lookup[task_id] for task_id in task_ids]

    monkeypatch.setattr(
        "eval.datasets.humaneval_adapter.load_humaneval_by_ids",
        _by_ids,
    )

    first = [task.task_id for task in load_humaneval_curated_hard(n=30, seed=42)]
    second = [task.task_id for task in load_humaneval_curated_hard(n=30, seed=42)]
    assert first == second
    assert len(first) == 30


def test_discriminative_alias_resolves_in_eval_yaml() -> None:
    """discriminative alias points at the frozen ids file with n=30 seed=42."""
    config = load_eval_config()
    block = config.discriminative
    assert block.get("dataset") == "humaneval"
    assert block.get("ids_file") == "humaneval_hard_ids.txt"
    assert int(block.get("sample_size", 0)) == 30
    assert int(block.get("seed", 0)) == 42
    assert block.get("curated_only") is True


def test_existing_humaneval_hard_alias_unchanged() -> None:
    """humaneval_hard alias remains the Phase-15 curated hard slice defaults."""
    config = load_eval_config()
    block = config.humaneval_hard
    assert block.get("difficulty") == "hard"
    assert int(block.get("sample_size", 0)) == 30
    assert int(block.get("seed", 0)) == 42
    assert block.get("curated_only") is True

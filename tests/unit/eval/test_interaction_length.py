"""Unit tests for synthetic multi-step tasks and interaction-length sweep."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.datasets.synthetic_multistep import (
    compile_check_source,
    generate_multistep,
)
from eval.scenarios.interaction_length import run_interaction_length
from framework.tools.compile_check import py_compile_check


def test_generated_tasks_are_deterministic() -> None:
    """Same seed produces identical task ids and prompts."""
    first = generate_multistep(levels=[2, 4], per_level=3, seed=99)
    second = generate_multistep(levels=[2, 4], per_level=3, seed=99)
    assert [task.task_id for task in first] == [task.task_id for task in second]
    assert [task.prompt for task in first] == [task.prompt for task in second]
    assert [task.test_code for task in first] == [task.test_code for task in second]


def test_required_steps_monotonic_with_level() -> None:
    """Each generated task's required_steps matches its level bucket."""
    tasks = generate_multistep(levels=[2, 4, 6, 8], per_level=5, seed=42)
    by_level: dict[int, list[int]] = {}
    for task in tasks:
        by_level.setdefault(task.required_steps, []).append(task.required_steps)
    assert set(by_level.keys()) == {2, 4, 6, 8}
    for level, values in by_level.items():
        assert all(value == level for value in values)
        assert len(values) == 5


def test_generated_test_code_compiles() -> None:
    """Reference solution plus assertions compile for every synthetic task."""
    tasks = generate_multistep(levels=[2, 4, 6, 8], per_level=2, seed=7)
    for task in tasks:
        result = py_compile_check(compile_check_source(task))
        assert result.ok, f"{task.task_id}: {result.errors}"


def test_run_interaction_length_dry_run_builds_all_levels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Dry-run sweep builds JSONL and manifests for every requested level."""
    monkeypatch.setattr("eval.scenarios.interaction_length._traces_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "eval.scenarios.interaction_length.manifest_provider_and_profiles",
        lambda: ("deepseek", "planner", "executor"),
    )
    monkeypatch.setattr(
        "eval.scenarios.interaction_length.resolve_git_sha",
        lambda _root=None: "deadbeef",
    )

    summary = run_interaction_length(
        "D",
        levels=[2, 4],
        seed=42,
        per_level=2,
        dry_run=True,
    )

    assert summary["dry_run"] is True
    assert set(summary["levels"].keys()) == {"2", "4"}
    for level in ("2", "4"):
        block = summary["levels"][level]
        assert block["n"] == 2
        trace_path = Path(block["trace_file"])
        assert trace_path.is_file()
        rows = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
        assert len(rows) == 2
        assert all(row["outcome"] == "dry_run" for row in rows)
        assert Path(block["manifest_file"]).is_file()

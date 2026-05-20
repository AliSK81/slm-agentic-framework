"""Unit tests for eval.run_quality (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from eval.run_quality import assess_run


def _write_jsonl(path: Path, interaction_counts: list[int]) -> None:
    """Write aggregate JSONL rows with given interaction counts."""
    lines = []
    for index, count in enumerate(interaction_counts):
        lines.append(
            json.dumps(
                {
                    "task_id": f"task-{index}",
                    "solved": False,
                    "outcome": "max_steps_reached",
                    "interaction_count": count,
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_assess_run_flags_all_zero_interaction_as_invalid(tmp_path: Path) -> None:
    """All tasks with interaction_count=0 → run INVALID."""
    jsonl = tmp_path / "run.jsonl"
    _write_jsonl(jsonl, [0, 0, 0, 0, 0])

    quality = assess_run(str(jsonl))

    assert quality.valid is False
    assert quality.zero_interaction_tasks == 5
    assert quality.reason is not None
    assert "interaction_count=0" in quality.reason


def test_assess_run_passes_when_all_tasks_interacted(tmp_path: Path) -> None:
    """No zero-interaction tasks → run valid."""
    jsonl = tmp_path / "run.jsonl"
    _write_jsonl(jsonl, [1, 2, 3, 4])

    quality = assess_run(str(jsonl))

    assert quality.valid is True
    assert quality.zero_interaction_tasks == 0
    assert quality.reason is None


def test_assess_run_threshold_boundary(tmp_path: Path) -> None:
    """Exactly 10% zero-interaction tasks → still valid (not strictly greater)."""
    jsonl = tmp_path / "run.jsonl"
    _write_jsonl(jsonl, [0] + [2] * 9)

    quality = assess_run(str(jsonl), max_zero_ix_fraction=0.10)

    assert quality.n_tasks == 10
    assert quality.zero_interaction_tasks == 1
    assert quality.valid is True

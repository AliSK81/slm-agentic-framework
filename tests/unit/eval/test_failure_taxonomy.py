"""Unit tests for failure taxonomy (phase 38)."""

from __future__ import annotations

import json
from pathlib import Path

from eval.metrics.failure_taxonomy import (
    classify_outcome,
    merge_taxonomies,
    taxonomy_from_trace,
)
from eval.metrics.sr import RunResult


def test_taxonomy_classifies_each_outcome_kind() -> None:
    """Each standard outcome maps to a taxonomy label."""
    assert classify_outcome("solved") == "solved"
    assert classify_outcome("escalate") == "escalate"
    assert classify_outcome("max_steps_reached") == "max_steps_reached"
    assert classify_outcome("unresolvable") == "unresolvable"
    assert classify_outcome("unknown") == "other"


def test_taxonomy_counts_per_config_and_provider(tmp_path: Path) -> None:
    """Trace aggregation produces counts keyed by outcome kind."""
    trace = tmp_path / "run.jsonl"
    rows = [
        RunResult(task_id="t1", solved=True, outcome="solved", interaction_count=1),
        RunResult(task_id="t2", solved=False, outcome="escalate", interaction_count=2),
        RunResult(
            task_id="t3",
            solved=False,
            outcome="max_steps_reached",
            interaction_count=3,
        ),
    ]
    trace.write_text(
        "\n".join(json.dumps(row.model_dump()) for row in rows) + "\n",
        encoding="utf-8",
    )
    summary = taxonomy_from_trace(trace, config="D", provider="deepseek")
    assert summary.total == 3
    assert summary.counts["solved"] == 1
    assert summary.counts["escalate"] == 1


def test_taxonomy_reads_decision_jsonl_not_checkpoints(tmp_path: Path) -> None:
    """Manifest decisions_file is accepted when present (no checkpoint requirement)."""
    trace = tmp_path / "D_discriminative_20260521T120000Z.jsonl"
    trace.write_text(
        json.dumps(
            RunResult(
                task_id="t0",
                solved=False,
                outcome="unresolvable",
                interaction_count=1,
            ).model_dump()
        )
        + "\n",
        encoding="utf-8",
    )
    decisions = tmp_path / "decisions" / "D_decisions.jsonl"
    decisions.parent.mkdir()
    decisions.write_text(
        json.dumps(
            {
                "task_id": "t0",
                "session_id": "sess-test",
                "step_index": 0,
                "kind": "act",
                "self_check_verdict": "pass",
                "by_agent": "executor",
                "rationale": "test",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "D_discriminative_20260521T120000Z.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "run_id": "D_discriminative_20260521T120000Z",
                "config": "D",
                "dataset": "discriminative",
                "seed": 42,
                "n": 1,
                "provider": "deepseek",
                "planner_profile": "deepseek-v4-flash",
                "executor_profile": "deepseek-v4-flash",
                "git_sha": "abc",
                "task_ids": ["t0"],
                "decisions_file": str(decisions),
                "task_to_session_map": {},
                "created_at": "2026-05-21T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    summary = taxonomy_from_trace(trace)
    assert summary.config == "D"
    assert summary.counts["unresolvable"] == 1


def test_taxonomy_merge_combines_runs() -> None:
    """merge_taxonomies sums counts across runs for the same config."""
    from eval.metrics.failure_taxonomy import TaxonomyCounts

    a = TaxonomyCounts(config="A", provider="p", counts={"solved": 2}, total=2)
    b = TaxonomyCounts(config="A", provider="p", counts={"escalate": 1}, total=1)
    merged = merge_taxonomies([a, b])
    assert len(merged) == 1
    assert merged[0].counts["solved"] == 2
    assert merged[0].counts["escalate"] == 1

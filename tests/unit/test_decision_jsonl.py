"""Unit tests for decision JSONL streaming and manifest task↔session map."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from eval.run_quality import RunQuality

from eval.decision_log import DecisionLogWriter, load_streamed_decisions
from eval.manifest import write_manifest
from eval.metrics import RunResult
from eval.run_eval import run_eval
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord


def _entry(session_id: str = "sess-abc", step: int = 0) -> DecisionEntry:
    return DecisionEntry(
        session_id=session_id,
        decision_id=f"d-{step}",
        step_index=step,
        by_agent="executor",
        kind="code_edit",
        payload={"file_path": "solution.py"},
        rationale="edit code",
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


def test_decision_entries_streamed_with_task_id(tmp_path: Path) -> None:
    """Each appended decision line carries the benchmark task_id."""
    log_path = tmp_path / "decisions" / "D_humaneval_run.jsonl"
    writer = DecisionLogWriter(log_path)
    writer.append(_entry(), task_id="HumanEval/42")

    rows = load_streamed_decisions(log_path)
    assert len(rows) == 1
    assert rows[0].task_id == "HumanEval/42"
    assert rows[0].session_id == "sess-abc"
    assert rows[0].kind == "code_edit"
    assert rows[0].self_check_verdict == "pass"


def test_memory_store_invokes_on_decision_hook(tmp_path: Path) -> None:
    """DecisionLog.on_append fires when decisions are committed."""
    seen: list[str] = []

    def hook(entry: DecisionEntry) -> None:
        seen.append(entry.decision_id)

    memory = MemoryStores.sqlite(tmp_path / "mem.db", on_decision=hook)
    memory.decisions.append(_entry())
    assert seen == ["d-0"]


def test_manifest_contains_task_to_session_map(tmp_path: Path) -> None:
    """Manifest records task_id to session_id mapping from eval runs."""
    path = write_manifest(
        "D_humaneval_test",
        traces_dir=tmp_path,
        config="D",
        dataset="humaneval",
        n=1,
        seed=42,
        provider="deepseek",
        planner_profile="p",
        executor_profile="e",
        git_sha="abc",
        task_ids=["HumanEval/0"],
        task_to_session_map={"HumanEval/0": "sess-map-1"},
        decisions_file=str(tmp_path / "decisions" / "D_humaneval_test.jsonl"),
        created_at=datetime.now(UTC),
    )
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task_to_session_map"]["HumanEval/0"] == "sess-map-1"
    assert "decisions" in payload["decisions_file"]


def test_run_eval_writes_task_to_session_map(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """run_eval populates manifest task_to_session_map from session outcomes."""
    monkeypatch.setattr("eval.run_eval._traces_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "eval.run_eval.manifest_provider_and_profiles",
        lambda: ("deepseek", "p", "e"),
    )
    monkeypatch.setattr("eval.run_eval.resolve_git_sha", lambda _root=None: "deadbeef")

    class FakeSession:
        session_id = "sess-from-eval"
        outcome = "solved"
        decision_count = 2
        step_count = 2
        retry_count = 0
        test_passed = True

    monkeypatch.setattr(
        "eval.run_eval._load_tasks_by_ids",
        lambda _ds, ids: [("HumanEval/0", "goal", ["c"], "assert True", None)],
    )

    def mock_run_single_task(*_args: object, **kwargs: object) -> RunResult:
        log_path = kwargs.get("decision_log_path")
        if log_path:
            DecisionLogWriter(Path(str(log_path))).append(_entry("sess-from-eval"), task_id="HumanEval/0")
        return RunResult(
            task_id="HumanEval/0",
            solved=True,
            outcome="solved",
            interaction_count=2,
            session_id="sess-from-eval",
            trace_path="traces/x.json",
        )

    monkeypatch.setattr(
        "eval.run_eval.assess_run",
        lambda _path: RunQuality(
            run_path="x",
            n_tasks=1,
            zero_interaction_tasks=0,
            valid=True,
        ),
    )

    with patch("eval.run_eval._run_single_task", side_effect=mock_run_single_task):
        summary = run_eval("D", "humaneval", task_ids=["HumanEval/0"], dry_run=False)

    import json

    manifest = json.loads(Path(summary["manifest_file"]).read_text(encoding="utf-8"))
    assert manifest["task_to_session_map"]["HumanEval/0"] == "sess-from-eval"
    assert Path(summary["decisions_file"]).is_file()

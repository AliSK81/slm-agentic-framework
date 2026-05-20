"""Unit tests for trace analysis scripts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eval.metrics import RunResult
from framework.memory.stores import DecisionEntry, Issue, SelfCheckRecord
from eval.decision_log import DecisionLogWriter
from eval.manifest import write_manifest
from framework.memory.stores import DecisionEntry, SelfCheckRecord
from scripts.analyze_traces import (
    check_behavioral_interpretability,
    count_contradictions,
    count_self_check_failures,
    extract_retry_curves,
    iter_decisions,
    load_jsonl_rows,
    resolve_session_id,
    summarize_trace,
)


def _write_jsonl(path: Path, rows: list[RunResult]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.model_dump(), default=str) + "\n")


def _write_checkpoint(path: Path, session_id: str, decisions: list[DecisionEntry]) -> None:
    payload = {
        "session_id": session_id,
        "step_index": 1,
        "stores": {
            "decisions": [d.model_dump(mode="json") for d in decisions],
            "state": [],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_jsonl_and_retry_curves(tmp_path: Path) -> None:
    """Retry curves derive attempts from retry_count in aggregate JSONL."""
    jsonl = tmp_path / "D_humaneval_test.jsonl"
    _write_jsonl(
        jsonl,
        [
            RunResult(
                task_id="HumanEval/1",
                solved=True,
                outcome="solved",
                interaction_count=2,
                retry_count=1,
            ),
        ],
    )
    curves = extract_retry_curves(str(jsonl))
    assert curves[0]["session_id"] == "HumanEval/1"
    assert curves[0]["attempts"] == 2


def test_count_self_check_failures_from_checkpoints(tmp_path: Path) -> None:
    """Self-check issue kinds are counted from checkpoint decision stores."""
    jsonl = tmp_path / "D_humaneval_test.jsonl"
    _write_jsonl(
        jsonl,
        [RunResult(task_id="t1", solved=False, outcome="escalate", interaction_count=1)],
    )
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    entry = DecisionEntry(
        session_id="sess-1",
        decision_id="d-1",
        step_index=0,
        by_agent="executor",
        kind="code_edit",
        payload={},
        rationale="because test",
        self_check=SelfCheckRecord(
            verdict="fail",
            issues=[
                Issue(kind="schema_violation", detail="bad json"),
                Issue(kind="contradiction", detail="conflict"),
            ],
        ),
        timestamp=datetime.now(UTC),
    )
    _write_checkpoint(ckpt_dir / "sess-1_000001.json", "sess-1", [entry])

    failures = count_self_check_failures(str(jsonl), checkpoint_dir=str(ckpt_dir))
    assert failures["schema_violation"] == 1
    assert failures["contradiction"] == 1
    assert count_contradictions(str(jsonl), checkpoint_dir=str(ckpt_dir)) == 1


def test_summarize_trace_computes_sr(tmp_path: Path) -> None:
    """Summary includes SR/CER from RunResult rows."""
    jsonl = tmp_path / "A_humaneval_test.jsonl"
    _write_jsonl(
        jsonl,
        [
            RunResult(task_id="a", solved=True, outcome="solved", interaction_count=1),
            RunResult(task_id="b", solved=False, outcome="escalate", interaction_count=1),
        ],
    )
    summary = summarize_trace(str(jsonl))
    assert summary["n"] == 2
    assert summary["sr"] == 50.0
    assert summary["cer"] == 50.0


def test_analyze_traces_joins_decisions_on_task_id(tmp_path: Path) -> None:
    """Decision JSONL is filtered by task_id via manifest session map."""
    jsonl = tmp_path / "D_humaneval_test.jsonl"
    _write_jsonl(
        jsonl,
        [
            RunResult(
                task_id="HumanEval/1",
                solved=False,
                outcome="escalate",
                interaction_count=3,
                session_id="sess-real",
            ),
        ],
    )
    decisions_path = tmp_path / "decisions" / "D_humaneval_test.jsonl"
    writer = DecisionLogWriter(decisions_path)
    writer.append(
        DecisionEntry(
            session_id="sess-real",
            decision_id="d-1",
            step_index=0,
            by_agent="executor",
            kind="code_edit",
            payload={},
            rationale="because",
            self_check=SelfCheckRecord(
                verdict="fail",
                issues=[],
            ),
            timestamp=datetime.now(UTC),
        ),
        task_id="HumanEval/1",
    )
    write_manifest(
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
        task_ids=["HumanEval/1"],
        task_to_session_map={"HumanEval/1": "sess-real"},
        decisions_file=str(decisions_path),
        created_at=datetime.now(UTC),
    )

    rows = list(iter_decisions(str(jsonl), task_id="HumanEval/1"))
    assert len(rows) == 1
    assert rows[0].session_id == "sess-real"
    assert resolve_session_id(str(jsonl), "HumanEval/1") == "sess-real"


def test_interpretability_dump_resolves_by_humaneval_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check_behavioral_interpretability accepts HumanEval ids, not only sess-*."""
    jsonl = tmp_path / "D_humaneval_test.jsonl"
    _write_jsonl(
        jsonl,
        [RunResult(task_id="HumanEval/9", solved=False, outcome="escalate", interaction_count=1)],
    )
    decisions_path = tmp_path / "decisions" / "D_humaneval_test.jsonl"
    DecisionLogWriter(decisions_path).append(
        DecisionEntry(
            session_id="sess-nine",
            decision_id="d-9",
            step_index=0,
            by_agent="planner",
            kind="plan_step",
            payload={"subtasks": ["step"]},
            rationale="plan it",
            self_check=SelfCheckRecord(verdict="pass", issues=[]),
            timestamp=datetime.now(UTC),
        ),
        task_id="HumanEval/9",
    )
    write_manifest(
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
        task_ids=["HumanEval/9"],
        task_to_session_map={"HumanEval/9": "sess-nine"},
        decisions_file=str(decisions_path),
        created_at=datetime.now(UTC),
    )

    check_behavioral_interpretability(str(jsonl), "HumanEval/9")
    captured = capsys.readouterr().out
    assert "sess-nine" in captured
    assert "plan_step" in captured

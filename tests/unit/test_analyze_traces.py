"""Unit tests for trace analysis scripts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eval.metrics import RunResult
from framework.memory.stores import DecisionEntry, Issue, SelfCheckRecord
from scripts.analyze_traces import (
    count_contradictions,
    count_self_check_failures,
    extract_retry_curves,
    load_jsonl_rows,
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

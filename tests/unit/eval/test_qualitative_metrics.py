"""Unit tests for deterministic qualitative metrics over decision JSONL."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eval.decision_log import DecisionLogWriter, StreamedDecisionLine
from eval.metrics import RunResult
from eval.metrics.qualitative import QualitativeReport, compute_qualitative
from framework.memory.stores import DecisionEntry, Issue, SelfCheckRecord


def _write_line(path: Path, line: StreamedDecisionLine) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line.model_dump(mode="json")) + "\n")


def _line(
    *,
    task_id: str = "HumanEval/1",
    session_id: str = "sess-1",
    step: int = 0,
    kind: str = "code_edit",
    rationale: str = "because",
    issues: list[str] | None = None,
    payload_hash: str = "aaa",
) -> StreamedDecisionLine:
    return StreamedDecisionLine(
        task_id=task_id,
        session_id=session_id,
        step_index=step,
        kind=kind,
        self_check_verdict="fail" if issues else "pass",
        rationale=rationale,
        self_check_issues=issues or [],
        payload_hash=payload_hash,
    )


def test_contradiction_rate_counts_contradiction_issues(tmp_path: Path) -> None:
    """contradiction_rate is the fraction of decisions with contradiction issues."""
    path = tmp_path / "decisions.jsonl"
    _write_line(path, _line(issues=["contradiction"]))
    _write_line(path, _line(step=1, issues=[]))

    report = compute_qualitative(str(path))

    assert report.contradiction_rate == 0.5
    assert report.n_decisions == 2


def test_rationale_coverage_full_when_all_have_rationale(tmp_path: Path) -> None:
    """rationale_coverage reaches 1.0 when every decision has non-empty rationale."""
    path = tmp_path / "decisions.jsonl"
    _write_line(path, _line(rationale="first"))
    _write_line(path, _line(step=1, rationale="second"))

    report = compute_qualitative(str(path))

    assert report.rationale_coverage == 1.0


def test_loop_rate_uses_quality_gate_loop_flag(tmp_path: Path) -> None:
    """loop_rate counts decisions whose self_check issues include loop."""
    path = tmp_path / "decisions.jsonl"
    _write_line(path, _line(issues=["loop"]))
    _write_line(path, _line(step=1, issues=["schema_violation"]))

    report = compute_qualitative(str(path))

    assert report.loop_rate == 0.5


def test_oscillation_index_detects_flip_flop_decisions(tmp_path: Path) -> None:
    """oscillation_index rises when same-kind steps alternate payload hashes."""
    path = tmp_path / "decisions.jsonl"
    _write_line(path, _line(step=0, kind="code_edit", payload_hash="hash-a"))
    _write_line(path, _line(step=1, kind="code_edit", payload_hash="hash-b"))
    _write_line(path, _line(step=2, kind="code_edit", payload_hash="hash-a"))

    report = compute_qualitative(str(path))

    assert report.oscillation_index > 0.0


def test_metrics_bucketed_by_interaction_length(tmp_path: Path) -> None:
    """by_interaction_length buckets metrics using aggregate JSONL interaction counts."""
    decisions_path = tmp_path / "decisions.jsonl"
    _write_line(
        decisions_path,
        _line(task_id="HumanEval/1", session_id="sess-1", step=0, issues=["contradiction"]),
    )
    _write_line(
        decisions_path,
        _line(
            task_id="HumanEval/2",
            session_id="sess-2",
            step=0,
            issues=[],
            payload_hash="x",
        ),
    )

    trace_path = tmp_path / "D_humaneval_test.jsonl"
    with trace_path.open("w", encoding="utf-8") as handle:
        for task_id, ix in (("HumanEval/1", 2), ("HumanEval/2", 5)):
            row = RunResult(
                task_id=task_id,
                solved=False,
                outcome="escalate",
                interaction_count=ix,
            )
            handle.write(json.dumps(row.model_dump(), default=str) + "\n")

    report = compute_qualitative(str(decisions_path), trace_path=str(trace_path))

    assert "2" in report.by_interaction_length
    assert "5+" in report.by_interaction_length
    assert report.by_interaction_length["2"]["contradiction_rate"] == 1.0
    assert report.by_interaction_length["5+"]["contradiction_rate"] == 0.0


def test_decision_log_writer_records_issue_kinds_and_payload_hash(tmp_path: Path) -> None:
    """Streaming writer persists fields required for qualitative metrics."""
    path = tmp_path / "run.jsonl"
    writer = DecisionLogWriter(path)
    entry = DecisionEntry(
        session_id="sess-w",
        decision_id="d-1",
        step_index=0,
        by_agent="executor",
        kind="code_edit",
        payload={"file_path": "solution.py", "content": "x = 1"},
        rationale="edit",
        self_check=SelfCheckRecord(
            verdict="fail",
            issues=[Issue(kind="loop", detail="repeated proposal")],
        ),
        timestamp=datetime.now(UTC),
    )
    writer.append(entry, task_id="HumanEval/99")

    report = compute_qualitative(str(path))
    assert isinstance(report, QualitativeReport)
    assert report.loop_rate == 1.0
    assert report.n_decisions == 1
    assert report.rationale_coverage == 1.0

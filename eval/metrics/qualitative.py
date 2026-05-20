"""Deterministic qualitative metrics over Phase-23 decision JSONL (RQ1/RQ2)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

from eval.decision_log import StreamedDecisionLine, load_streamed_decisions
from eval.metrics.sr import RunResult


class QualitativeReport(BaseModel):
    """Coherence, interpretability, and stability metrics for one eval run."""

    contradiction_rate: float = 0.0
    rationale_coverage: float = 0.0
    loop_rate: float = 0.0
    oscillation_index: float = 0.0
    by_interaction_length: dict[str, dict[str, float]] = Field(default_factory=dict)
    n_decisions: int = 0


def _has_issue(line: StreamedDecisionLine, kind: str) -> bool:
    return kind in line.self_check_issues


def _session_oscillation(lines: list[StreamedDecisionLine]) -> float:
    """Fraction of adjacent same-kind steps with differing payload hash."""
    ordered = sorted(lines, key=lambda row: row.step_index)
    if len(ordered) < 2:
        return 0.0
    swaps = 0
    for index in range(1, len(ordered)):
        prev, curr = ordered[index - 1], ordered[index]
        if prev.kind == curr.kind and prev.payload_hash != curr.payload_hash:
            swaps += 1
    return swaps / (len(ordered) - 1)


def _metrics_for_lines(lines: list[StreamedDecisionLine]) -> dict[str, float]:
    """Compute core rates for a subset of decision lines."""
    total = len(lines)
    if total == 0:
        return {
            "contradiction_rate": 0.0,
            "rationale_coverage": 0.0,
            "loop_rate": 0.0,
            "oscillation_index": 0.0,
            "n_decisions": 0.0,
        }

    contradiction_hits = sum(1 for line in lines if _has_issue(line, "contradiction"))
    loop_hits = sum(1 for line in lines if _has_issue(line, "loop"))
    rationale_hits = sum(1 for line in lines if line.rationale.strip())

    by_session: dict[str, list[StreamedDecisionLine]] = defaultdict(list)
    for line in lines:
        by_session[line.session_id].append(line)
    oscillation = (
        sum(_session_oscillation(session_lines) for session_lines in by_session.values())
        / len(by_session)
    )

    return {
        "contradiction_rate": contradiction_hits / total,
        "rationale_coverage": rationale_hits / total,
        "loop_rate": loop_hits / total,
        "oscillation_index": oscillation,
        "n_decisions": float(total),
    }


def _interaction_length_map(trace_path: str) -> dict[str, int]:
    """Map task_id to interaction_count from aggregate JSONL."""
    path = Path(trace_path)
    if not path.is_file():
        return {}
    mapping: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = RunResult.model_validate(json.loads(raw))
        mapping[row.task_id] = max(row.interaction_count, 0)
    return mapping


def _bucket_label(interaction_count: int) -> str:
    """Bucket interaction counts for trajectory reporting."""
    if interaction_count <= 0:
        return "0"
    if interaction_count <= 4:
        return str(interaction_count)
    return "5+"


def compute_qualitative(
    decisions_jsonl: str,
    *,
    trace_path: str | None = None,
) -> QualitativeReport:
    """Compute qualitative metrics from a decision JSONL file.

    Inputs:
        decisions_jsonl: Path to ``traces/decisions/{run_id}.jsonl``.
        trace_path: Optional aggregate JSONL to bucket metrics by interaction_count.

    Outputs:
        :class:`QualitativeReport` with rates in [0, 1] unless empty input.
    """
    lines = load_streamed_decisions(decisions_jsonl)
    core = _metrics_for_lines(lines)

    by_ix: dict[str, dict[str, float]] = {}
    if trace_path:
        ix_map = _interaction_length_map(trace_path)
        buckets: dict[str, list[StreamedDecisionLine]] = defaultdict(list)
        for line in lines:
            label = _bucket_label(ix_map.get(line.task_id, 0))
            buckets[label].append(line)
        for label, bucket_lines in sorted(buckets.items()):
            subset = _metrics_for_lines(bucket_lines)
            by_ix[label] = {
                key: subset[key]
                for key in (
                    "contradiction_rate",
                    "rationale_coverage",
                    "loop_rate",
                    "oscillation_index",
                )
            }

    return QualitativeReport(
        contradiction_rate=core["contradiction_rate"],
        rationale_coverage=core["rationale_coverage"],
        loop_rate=core["loop_rate"],
        oscillation_index=core["oscillation_index"],
        by_interaction_length=by_ix,
        n_decisions=int(core["n_decisions"]),
    )


def compare_qualitative(
    report_a: QualitativeReport,
    report_b: QualitativeReport,
    *,
    label_a: str = "A",
    label_b: str = "D",
) -> dict[str, dict[str, float]]:
    """Compare two reports (e.g. ablation A vs D) on key stability/coherence deltas."""
    return {
        "contradiction_rate": {
            label_a: report_a.contradiction_rate,
            label_b: report_b.contradiction_rate,
            "delta": report_b.contradiction_rate - report_a.contradiction_rate,
        },
        "oscillation_index": {
            label_a: report_a.oscillation_index,
            label_b: report_b.oscillation_index,
            "delta": report_b.oscillation_index - report_a.oscillation_index,
        },
        "loop_rate": {
            label_a: report_a.loop_rate,
            label_b: report_b.loop_rate,
            "delta": report_b.loop_rate - report_a.loop_rate,
        },
        "rationale_coverage": {
            label_a: report_a.rationale_coverage,
            label_b: report_b.rationale_coverage,
            "delta": report_b.rationale_coverage - report_a.rationale_coverage,
        },
    }

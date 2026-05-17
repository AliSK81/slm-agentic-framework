#!/usr/bin/env python3
"""Inspect evaluation traces and checkpoint decision logs."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from framework.memory.stores import DecisionEntry
from eval.metrics import RunResult, compute_cer, compute_sr


def _resolve_path(trace_path: str) -> Path:
    return Path(trace_path).expanduser().resolve()


def _default_checkpoint_dir(trace_path: Path) -> Path:
    """Prefer ``traces/checkpoints`` adjacent to aggregate JSONL under ``traces/``."""
    if trace_path.parent.name == "traces" or trace_path.parent.parent.name == "traces":
        candidate = trace_path.parent / "checkpoints"
        if candidate.is_dir():
            return candidate
    root = _PROJECT_ROOT / "traces" / "checkpoints"
    return root


def load_jsonl_rows(trace_path: str) -> list[RunResult]:
    """Load aggregate JSONL written by ``run_eval`` / ablation."""
    path = _resolve_path(trace_path)
    rows: list[RunResult] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(RunResult.model_validate(json.loads(line)))
    return rows


def _iter_decisions(checkpoint_dir: Path) -> Iterator[DecisionEntry]:
    """Yield decision entries from all complete checkpoint files."""
    if not checkpoint_dir.is_dir():
        return
    for path in sorted(checkpoint_dir.glob("*.json")):
        if path.name.endswith(".tmp"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get("stores", {}).get("decisions", []):
            try:
                yield DecisionEntry.model_validate(row)
            except Exception:
                continue


def count_self_check_failures(
    trace_path: str,
    *,
    checkpoint_dir: str | None = None,
) -> dict[str, int]:
    """Count schema_violation, contradiction, scope_violation from checkpoint logs."""
    path = _resolve_path(trace_path)
    ckpt = Path(checkpoint_dir) if checkpoint_dir else _default_checkpoint_dir(path)
    counts: Counter[str] = Counter()
    for entry in _iter_decisions(ckpt):
        if entry.self_check.verdict in ("pass",):
            continue
        for issue in entry.self_check.issues:
            counts[str(issue.kind)] += 1
        if not entry.self_check.issues and entry.self_check.verdict == "exhausted":
            counts["exhausted"] += 1
    return dict(counts)


def count_contradictions(
    trace_path: str,
    *,
    checkpoint_dir: str | None = None,
) -> int:
    """Count decision log entries with at least one contradiction issue."""
    path = _resolve_path(trace_path)
    ckpt = Path(checkpoint_dir) if checkpoint_dir else _default_checkpoint_dir(path)
    total = 0
    for entry in _iter_decisions(ckpt):
        if any(issue.kind == "contradiction" for issue in entry.self_check.issues):
            total += 1
    return total


def extract_retry_curves(trace_path: str) -> list[dict[str, Any]]:
    """Per task: session_id (task_id), subtask_id, attempts from aggregate JSONL."""
    rows = load_jsonl_rows(trace_path)
    curves: list[dict[str, Any]] = []
    for row in rows:
        curves.append(
            {
                "session_id": row.task_id,
                "subtask_id": "main",
                "attempts": max(row.retry_count, 0) + 1,
                "interaction_count": row.interaction_count,
                "solved": row.solved,
            }
        )
    return curves


def _find_session_checkpoints(checkpoint_dir: Path, session_id: str) -> list[Path]:
    return sorted(checkpoint_dir.glob(f"{session_id}_*.json"))


def check_behavioral_interpretability(
    trace_path: str,
    session_id: str,
    *,
    checkpoint_dir: str | None = None,
) -> None:
    """Print decision log and state snapshots for one session in readable form."""
    path = _resolve_path(trace_path)
    ckpt = Path(checkpoint_dir) if checkpoint_dir else _default_checkpoint_dir(path)
    files = _find_session_checkpoints(ckpt, session_id)
    if not files:
        print(f"No checkpoints for session {session_id!r} under {ckpt}")
        rows = load_jsonl_rows(trace_path)
        match = [r for r in rows if r.task_id == session_id]
        if match:
            print("Aggregate JSONL row:")
            print(json.dumps(match[-1].model_dump(), indent=2, default=str))
        return

    latest = files[-1]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    print(f"=== Checkpoint {latest.name} (step {payload.get('step_index')}) ===\n")
    decisions = payload.get("stores", {}).get("decisions", [])
    print(f"--- Decisions ({len(decisions)}) ---")
    for row in decisions:
        entry = DecisionEntry.model_validate(row)
        print(
            f"[{entry.step_index}] {entry.by_agent}/{entry.kind} "
            f"self_check={entry.self_check.verdict}"
        )
        print(f"  rationale: {entry.rationale[:200]}")
        if entry.self_check.issues:
            for issue in entry.self_check.issues:
                print(f"  - {issue.kind}: {issue.detail}")
        print(f"  payload keys: {list(entry.payload.keys())}")
        print()

    states = payload.get("stores", {}).get("state", [])
    print(f"--- State snapshots ({len(states)}) ---")
    for row in states[-5:]:
        print(json.dumps(row, indent=2, default=str)[:800])
        print()


def summarize_trace(trace_path: str, *, checkpoint_dir: str | None = None) -> dict[str, Any]:
    """Summary metrics for report generation."""
    rows = load_jsonl_rows(trace_path)
    return {
        "trace_path": str(_resolve_path(trace_path)),
        "n": len(rows),
        "sr": compute_sr(rows),
        "cer": compute_cer(rows),
        "self_check_failures": count_self_check_failures(
            trace_path, checkpoint_dir=checkpoint_dir
        ),
        "contradictions": count_contradictions(
            trace_path, checkpoint_dir=checkpoint_dir
        ),
        "retry_curves": extract_retry_curves(trace_path),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI for trace inspection."""
    parser = argparse.ArgumentParser(description="Analyze evaluation traces")
    parser.add_argument(
        "--trace",
        required=True,
        help="Path to aggregate JSONL (e.g. traces/D_humaneval_*.jsonl)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Directory of session checkpoints (default: traces/checkpoints)",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Session or task id for behavioral interpretability dump",
    )
    args = parser.parse_args(argv)

    summary = summarize_trace(args.trace, checkpoint_dir=args.checkpoint_dir)
    print(json.dumps({k: v for k, v in summary.items() if k != "retry_curves"}, indent=2))
    curves = summary["retry_curves"]
    if curves:
        avg_attempts = sum(c["attempts"] for c in curves) / len(curves)
        print(f"\nRetry curves: n={len(curves)} avg_attempts={avg_attempts:.2f}")

    if args.session:
        print()
        check_behavioral_interpretability(
            args.trace,
            args.session,
            checkpoint_dir=args.checkpoint_dir,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

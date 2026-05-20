#!/usr/bin/env python3
"""Inspect evaluation traces, decision JSONL, and checkpoint decision logs."""

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

from eval.decision_log import StreamedDecisionLine, load_streamed_decisions
from eval.manifest import RunManifest
from eval.metrics import RunResult, compute_cer, compute_sr
from datetime import UTC, datetime

from framework.memory.stores import DecisionEntry, SelfCheckRecord


def _resolve_path(trace_path: str) -> Path:
    return Path(trace_path).expanduser().resolve()


def manifest_path_for_trace(trace_path: Path) -> Path:
    """Resolve ``traces/{run_id}.manifest.json`` next to aggregate JSONL."""
    return trace_path.with_name(f"{trace_path.stem}.manifest.json")


def load_run_manifest(trace_path: str) -> RunManifest | None:
    """Load the run manifest for an aggregate JSONL path, if present."""
    path = manifest_path_for_trace(_resolve_path(trace_path))
    if not path.is_file():
        return None
    return RunManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def resolve_session_id(trace_path: str, task_or_session_id: str) -> str:
    """Map a benchmark ``task_id`` to ``session_id`` via manifest; pass through sess-* ids."""
    if task_or_session_id.startswith("sess-"):
        return task_or_session_id
    manifest = load_run_manifest(trace_path)
    if manifest is None:
        return task_or_session_id
    return manifest.task_to_session_map.get(task_or_session_id, task_or_session_id)


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


def _decisions_jsonl_path(trace_path: str) -> Path | None:
    manifest = load_run_manifest(trace_path)
    if manifest is None or not manifest.decisions_file:
        return None
    path = Path(manifest.decisions_file)
    return path if path.is_file() else None


def _iter_decisions_from_jsonl(
    trace_path: str,
    *,
    task_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[DecisionEntry]:
    """Yield :class:`DecisionEntry` rows from streamed decision JSONL."""
    path = _decisions_jsonl_path(trace_path)
    if path is None:
        return
    for line in load_streamed_decisions(path):
        if task_id is not None and line.task_id != task_id:
            continue
        if session_id is not None and line.session_id != session_id:
            continue
        yield DecisionEntry(
            session_id=line.session_id,
            decision_id=line.decision_id or f"d-{line.step_index}",
            step_index=line.step_index,
            by_agent=line.by_agent or "executor",  # type: ignore[arg-type]
            kind=line.kind or "code_edit",  # type: ignore[arg-type]
            payload={},
            rationale=line.rationale,
            references=[],
            self_check=SelfCheckRecord(
                verdict=line.self_check_verdict,  # type: ignore[arg-type]
                issues=[],
            ),
            timestamp=datetime.now(UTC),
        )


def _iter_decisions_from_checkpoints(checkpoint_dir: Path) -> Iterator[DecisionEntry]:
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


def iter_decisions(
    trace_path: str,
    *,
    checkpoint_dir: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
) -> Iterator[DecisionEntry]:
    """Prefer decision JSONL; fall back to checkpoint stores."""
    resolved_session = session_id
    if task_id and not resolved_session:
        resolved_session = resolve_session_id(trace_path, task_id)

    jsonl_count = 0
    for entry in _iter_decisions_from_jsonl(
        trace_path,
        task_id=task_id,
        session_id=resolved_session,
    ):
        jsonl_count += 1
        yield entry

    if jsonl_count > 0:
        return

    path = _resolve_path(trace_path)
    ckpt = Path(checkpoint_dir) if checkpoint_dir else _default_checkpoint_dir(path)
    for entry in _iter_decisions_from_checkpoints(ckpt):
        if resolved_session and entry.session_id != resolved_session:
            continue
        yield entry


def count_self_check_failures(
    trace_path: str,
    *,
    checkpoint_dir: str | None = None,
    task_id: str | None = None,
) -> dict[str, int]:
    """Count schema_violation, contradiction, scope_violation from decision logs."""
    counts: Counter[str] = Counter()
    for entry in iter_decisions(
        trace_path, checkpoint_dir=checkpoint_dir, task_id=task_id
    ):
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
    task_id: str | None = None,
) -> int:
    """Count decision log entries with at least one contradiction issue."""
    total = 0
    for entry in iter_decisions(
        trace_path, checkpoint_dir=checkpoint_dir, task_id=task_id
    ):
        if any(issue.kind == "contradiction" for issue in entry.self_check.issues):
            total += 1
    return total


def extract_retry_curves(trace_path: str) -> list[dict[str, Any]]:
    """Per task: task_id, session_id, attempts from aggregate JSONL."""
    rows = load_jsonl_rows(trace_path)
    manifest = load_run_manifest(trace_path)
    curves: list[dict[str, Any]] = []
    for row in rows:
        session_id = row.session_id
        if not session_id and manifest is not None:
            session_id = manifest.task_to_session_map.get(row.task_id, "")
        curves.append(
            {
                "task_id": row.task_id,
                "session_id": session_id or row.task_id,
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
    task_or_session_id: str,
    *,
    checkpoint_dir: str | None = None,
) -> None:
    """Print decision log for a task id (via manifest map) or raw session id."""
    path = _resolve_path(trace_path)
    session_id = resolve_session_id(trace_path, task_or_session_id)
    task_id = task_or_session_id if not task_or_session_id.startswith("sess-") else None

    decisions = list(
        iter_decisions(
            trace_path,
            checkpoint_dir=checkpoint_dir,
            task_id=task_id,
            session_id=session_id,
        )
    )
    if decisions:
        label = task_or_session_id if task_id else session_id
        print(f"=== Decisions for {label!r} (session {session_id!r}, n={len(decisions)}) ===\n")
        for entry in decisions:
            print(
                f"[{entry.step_index}] {entry.by_agent}/{entry.kind} "
                f"self_check={entry.self_check.verdict}"
            )
            print(f"  rationale: {entry.rationale[:200]}")
            if entry.self_check.issues:
                for issue in entry.self_check.issues:
                    print(f"  - {issue.kind}: {issue.detail}")
            print()
        return

    ckpt = Path(checkpoint_dir) if checkpoint_dir else _default_checkpoint_dir(path)
    files = _find_session_checkpoints(ckpt, session_id)
    if not files:
        print(f"No decisions or checkpoints for {task_or_session_id!r} (session {session_id!r})")
        rows = load_jsonl_rows(trace_path)
        match = [r for r in rows if r.task_id == task_or_session_id]
        if match:
            print("Aggregate JSONL row:")
            print(json.dumps(match[-1].model_dump(), indent=2, default=str))
        return

    latest = files[-1]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    print(f"=== Checkpoint {latest.name} (step {payload.get('step_index')}) ===\n")
    for row in payload.get("stores", {}).get("decisions", []):
        entry = DecisionEntry.model_validate(row)
        print(
            f"[{entry.step_index}] {entry.by_agent}/{entry.kind} "
            f"self_check={entry.self_check.verdict}"
        )
        print(f"  rationale: {entry.rationale[:200]}")
        print()


def summarize_trace(trace_path: str, *, checkpoint_dir: str | None = None) -> dict[str, Any]:
    """Summary metrics for report generation."""
    rows = load_jsonl_rows(trace_path)
    manifest = load_run_manifest(trace_path)
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
        "task_to_session_map": manifest.task_to_session_map if manifest else {},
        "decisions_file": manifest.decisions_file if manifest else "",
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
        help="Task id (e.g. HumanEval/0) or session id for interpretability dump",
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

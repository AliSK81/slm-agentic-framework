"""Deterministic run-level quality gate over aggregate eval JSONL (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class RunQuality(BaseModel):
    """Quality assessment for one aggregate eval run."""

    run_path: str
    n_tasks: int
    zero_interaction_tasks: int
    valid: bool
    reason: str | None = None


def assess_run(
    run_path: str,
    max_zero_ix_fraction: float = 0.10,
) -> RunQuality:
    """Assess whether an aggregate JSONL run is valid for scoring.

    A run is INVALID when more than ``max_zero_ix_fraction`` of tasks have
    ``interaction_count == 0`` (infrastructure / zero-work failure mode).

    Inputs:
        run_path: Path to aggregate ``.jsonl`` trace file.
        max_zero_ix_fraction: Maximum allowed fraction of zero-interaction tasks.

    Outputs:
        RunQuality with ``valid=False`` and ``reason`` when the run is invalid.

    Side effects:
        Reads ``run_path`` from disk; raises FileNotFoundError if missing.
    """
    path = Path(run_path)
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))

    n_tasks = len(rows)
    zero_ix = sum(
        1 for row in rows if int(row.get("interaction_count", 0) or 0) == 0
    )

    if n_tasks == 0:
        return RunQuality(
            run_path=str(path),
            n_tasks=0,
            zero_interaction_tasks=0,
            valid=True,
            reason=None,
        )

    fraction = zero_ix / n_tasks
    if fraction > max_zero_ix_fraction:
        return RunQuality(
            run_path=str(path),
            n_tasks=n_tasks,
            zero_interaction_tasks=zero_ix,
            valid=False,
            reason=(
                f"{zero_ix}/{n_tasks} tasks have interaction_count=0 "
                f"({fraction:.0%} > {max_zero_ix_fraction:.0%} threshold)"
            ),
        )

    return RunQuality(
        run_path=str(path),
        n_tasks=n_tasks,
        zero_interaction_tasks=zero_ix,
        valid=True,
        reason=None,
    )

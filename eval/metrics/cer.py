"""Control-effort ratio (CER) metric."""

from __future__ import annotations

from eval.metrics.sr import RunResult


def compute_cer(results: list[RunResult]) -> float:
    """Compute CER = failed_interactions / total_interactions * 100."""
    total_interactions = sum(row.interaction_count for row in results)
    if total_interactions == 0:
        return 0.0
    failed_interactions = sum(
        row.interaction_count for row in results if not row.solved
    )
    return (failed_interactions / total_interactions) * 100.0

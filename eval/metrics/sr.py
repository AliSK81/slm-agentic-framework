"""Success rate (SR) metric."""

from __future__ import annotations

from eval.metrics.results import RunResult


def compute_sr(results: list[RunResult]) -> float:
    """Compute SR = solved / total * 100."""
    if not results:
        return 0.0
    solved = sum(1 for row in results if row.solved)
    return (solved / len(results)) * 100.0

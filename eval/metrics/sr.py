"""Success rate (SR) metric and per-run result model."""

from __future__ import annotations

from pydantic import BaseModel


class RunResult(BaseModel):
    """Outcome of one benchmark task run."""

    task_id: str
    solved: bool
    outcome: str  # solved | max_steps_reached | unresolvable | escalate
    interaction_count: int = 0
    step_count: int = 0
    retry_count: int = 0
    trace_path: str = ""
    session_id: str = ""
    tokens_total: int = 0
    latency_ms_total: int = 0
    llm_calls: int = 0
    model_id: str = ""


def compute_sr(results: list[RunResult]) -> float:
    """Compute SR = solved / total * 100."""
    if not results:
        return 0.0
    solved = sum(1 for row in results if row.solved)
    return (solved / len(results)) * 100.0

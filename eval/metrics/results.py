"""Shared evaluation result models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RunResult(BaseModel):
    """Outcome of one benchmark task run."""

    task_id: str
    solved: bool
    outcome: str  # solved | max_steps_reached | unresolvable | escalate
    interaction_count: int = 0
    step_count: int = 0
    retry_count: int = 0
    trace_path: str = ""
    config: str = ""
    dataset: str = ""
    error: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

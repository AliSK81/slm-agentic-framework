"""Control-layer Pydantic models for the Decision Cycle."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from framework.memory.stores import DecisionEntry
from framework.error_control.quality import QualityGate


class SLMProposal(BaseModel):
    """Parsed SLM JSON before self-check and log persistence."""

    kind: Literal[
        "plan_step",
        "code_edit",
        "tool_call",
        "handoff",
        "terminate",
        "reflection",
        "quality_failure",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    references: list[str] = Field(default_factory=list)


class CycleResult(BaseModel):
    """Outcome of one Decision Cycle invocation."""

    decision: DecisionEntry | None = None
    outcome: Any = None
    retry_count: int = 0
    exhausted: bool = False
    budget_exceeded: bool = False


class ErrorControlBundle(BaseModel):
    """Grouped error-control utilities for the cycle."""

    quality_gate: QualityGate = Field(default_factory=QualityGate)

    model_config = {"arbitrary_types_allowed": True}

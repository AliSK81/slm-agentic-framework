"""Control-layer Pydantic models for the Decision Cycle."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, ValidationError

from framework.memory.stores import DecisionEntry
from framework.error_control.quality import QualityGate

TurnType = Literal["answer", "inspect", "edit", "build"]
InteractivePhase = Literal["declaring", "bound"]


class InteractiveTurnState(BaseModel):
    """Framework-owned interactive turn state (budget/permissions from declared turn_type)."""

    declared_type: TurnType | None = None
    phase: InteractivePhase = "declaring"
    max_steps: int = 1
    read_only: bool = True
    bound: bool = False


class TerminatePayload(BaseModel):
    """Typed payload for ``kind=terminate`` decisions (interactive product mode)."""

    user_message: str = Field(
        default="",
        validation_alias=AliasChoices(
            "user_message",
            "answer",
            "summary",
            "response",
        ),
    )
    turn_type: TurnType | None = None


def parse_terminate_payload(payload: dict[str, Any] | None) -> TerminatePayload:
    """Validate and normalize a terminate payload dict."""
    return TerminatePayload.model_validate(payload or {})


def user_message_from_payload(
    payload: dict[str, Any] | None,
    *,
    fallback_rationale: str = "",
) -> str:
    """Return ``user_message`` from a terminate payload; optional legacy rationale fallback."""
    try:
        parsed = parse_terminate_payload(payload)
    except ValidationError:
        return fallback_rationale.strip()
    msg = parsed.user_message.strip()
    if msg:
        return msg
    return fallback_rationale.strip()


NEEDS_PLAN_REASON = "needs_plan"


def is_needs_plan_handoff(decision: DecisionEntry | None) -> bool:
    """Return True when an executor handoff requests full planner promotion."""
    if decision is None or decision.kind != "handoff":
        return False
    reason = str(decision.payload.get("reason", "")).strip().lower()
    if reason == NEEDS_PLAN_REASON:
        return True
    return decision.rationale.strip().lower() == NEEDS_PLAN_REASON


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

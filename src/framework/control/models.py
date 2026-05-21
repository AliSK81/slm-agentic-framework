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


HandoffReason = Literal["needs_edit", "needs_run", "needs_plan"]
NEEDS_PLAN_REASON: HandoffReason = "needs_plan"
NEEDS_EDIT_REASON: HandoffReason = "needs_edit"
NEEDS_RUN_REASON: HandoffReason = "needs_run"
_VALID_HANDOFF_REASONS = frozenset({"needs_edit", "needs_run", "needs_plan"})


class HandoffPayload(BaseModel):
    """Typed payload for ``kind=handoff`` (compound-turn phase promotion)."""

    reason: HandoffReason


def parse_handoff_payload(payload: dict[str, Any] | None) -> HandoffPayload | None:
    """Validate handoff payload; return None when reason is missing or invalid."""
    if not payload:
        return None
    raw = str(payload.get("reason", "")).strip().lower()
    if raw not in _VALID_HANDOFF_REASONS:
        return None
    try:
        return HandoffPayload(reason=raw)  # type: ignore[arg-type]
    except ValidationError:
        return None


def handoff_reason(decision: DecisionEntry | None) -> HandoffReason | None:
    """Return typed handoff reason from a decision, if present."""
    if decision is None or decision.kind != "handoff":
        return None
    parsed = parse_handoff_payload(decision.payload)
    if parsed is not None:
        return parsed.reason
    return None


def is_needs_plan_handoff(decision: DecisionEntry | None) -> bool:
    """Return True when an executor handoff requests full planner promotion."""
    return handoff_reason(decision) == NEEDS_PLAN_REASON


def is_needs_edit_handoff(decision: DecisionEntry | None) -> bool:
    """Return True when handoff requests promotion to the edit phase."""
    return handoff_reason(decision) == NEEDS_EDIT_REASON


def is_needs_run_handoff(decision: DecisionEntry | None) -> bool:
    """Return True when handoff requests promotion to the run/verify phase."""
    return handoff_reason(decision) == NEEDS_RUN_REASON


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

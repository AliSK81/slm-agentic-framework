"""Deterministic SELF_CHECK for Decision Cycle proposals."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from framework.control.interactive import (
    InteractiveCompletionState,
    icp_issues,
    turn_type_from_payload,
)
from framework.control.models import (
    handoff_reason,
    parse_terminate_payload,
)
from framework.memory.stores import DecisionEntry, Issue, MemoryStores, SelfCheckRecord

logger = logging.getLogger(__name__)

_PLANNER_ONLY_KINDS = frozenset({"plan_step"})
_EXECUTOR_ONLY_KINDS = frozenset(
    {"code_edit", "tool_call", "reflection", "quality_failure"}
)
_SHARED_KINDS = frozenset({"handoff"})
# Payload keys that may change between retries or turns (not logical contradictions).
_RETRY_VARYING_KEYS = frozenset(
    {
        "old_string",
        "new_string",
        "content",
        "code",
        "target",
        "path",
        "file_path",
        "file",
        "rationale",
        "user_message",
        "turn_type",
        "reason",
        "tool",
        "name",
        "function",
        "command",
    }
)


def _schema_issues(proposal: DecisionEntry) -> list[Issue]:
    """Re-validate proposal against DecisionEntry schema."""
    try:
        DecisionEntry.model_validate(proposal.model_dump())
    except ValidationError as exc:
        return [
            Issue(kind="schema_violation", detail=str(exc.errors()[0]["msg"]))
        ]
    return []


def _contradiction_issues(
    proposal: DecisionEntry,
    recent: list[DecisionEntry],
) -> list[Issue]:
    """Same kind + payload key with different value vs last 10 decisions."""
    if proposal.kind == "tool_call":
        return []
    issues: list[Issue] = []
    window = recent[-10:]
    for entry in window:
        if entry.decision_id == proposal.decision_id:
            continue
        if entry.kind != proposal.kind:
            continue
        for key, value in proposal.payload.items():
            if key in _RETRY_VARYING_KEYS:
                continue
            if key in entry.payload and entry.payload[key] != value:
                issues.append(
                    Issue(
                        kind="contradiction",
                        detail=(
                            f"payload[{key!r}]={value!r} conflicts with "
                            f"prior {entry.decision_id} value {entry.payload[key]!r}"
                        ),
                    )
                )
    return issues


def _scope_issues(proposal: DecisionEntry) -> list[Issue]:
    """Executor must not plan; planner must not invoke tools."""
    issues: list[Issue] = []
    if proposal.kind not in _SHARED_KINDS:
        if proposal.by_agent == "executor" and proposal.kind in _PLANNER_ONLY_KINDS:
            issues.append(
                Issue(
                    kind="scope_violation",
                    detail=f"executor cannot emit kind={proposal.kind}",
                )
            )
        if proposal.by_agent == "planner" and proposal.kind in _EXECUTOR_ONLY_KINDS:
            issues.append(
                Issue(
                    kind="scope_violation",
                    detail=f"planner cannot emit kind={proposal.kind}",
                )
            )
    return issues


def _rationale_issues(proposal: DecisionEntry) -> list[Issue]:
    if not proposal.rationale or not proposal.rationale.strip():
        return [Issue(kind="empty", detail="rationale is required")]
    return []


def _turn_type_required_issues(
    proposal: DecisionEntry,
    *,
    require_turn_type: bool,
) -> list[Issue]:
    """Require payload.turn_type on the first interactive cycle-1 proposal."""
    if not require_turn_type:
        return []
    if turn_type_from_payload(proposal.payload) is not None:
        return []
    raw = str((proposal.payload or {}).get("turn_type", "")).strip()
    if not raw:
        return [
            Issue(
                kind="turn_type_required",
                detail="payload.turn_type is required on cycle 1 (answer|inspect|edit|build)",
            )
        ]
    return [
        Issue(
            kind="turn_type_required",
            detail=f"invalid turn_type: {raw!r} (use answer|inspect|edit|build)",
        )
    ]


def _finalizer_only_issues(
    proposal: DecisionEntry,
    *,
    finalizer_only: bool,
) -> list[Issue]:
    """Finalizer cycle accepts only terminate proposals."""
    if not finalizer_only:
        return []
    if proposal.kind == "terminate":
        return []
    return [
        Issue(
            kind="finalizer_terminate_only",
            detail=f"finalizer cycle allows only terminate; got kind={proposal.kind}",
        )
    ]


def _handoff_payload_issues(proposal: DecisionEntry) -> list[Issue]:
    """Require typed handoff reason (needs_edit | needs_run | needs_plan)."""
    if proposal.kind != "handoff":
        return []
    if handoff_reason(proposal) is not None:
        return []
    return [
        Issue(
            kind="schema_violation",
            detail="handoff payload.reason must be needs_edit, needs_run, or needs_plan",
        )
    ]


def _terminate_payload_issues(proposal: DecisionEntry) -> list[Issue]:
    """Validate typed terminate payload when kind is terminate."""
    if proposal.kind != "terminate":
        return []
    try:
        parse_terminate_payload(proposal.payload)
    except ValidationError as exc:
        return [
            Issue(kind="schema_violation", detail=str(exc.errors()[0]["msg"]))
        ]
    return []


def self_check(
    proposal: DecisionEntry,
    memory: MemoryStores,
    session_id: str,
    *,
    require_turn_type: bool = False,
    icp: InteractiveCompletionState | None = None,
    finalizer_only: bool = False,
) -> SelfCheckRecord:
    """Run schema, contradiction, scope, and rationale checks."""
    _ = session_id  # reserved for session-scoped rules in later phases
    recent = memory.decisions.get_last_n(proposal.session_id, 10)
    issues: list[Issue] = []
    issues.extend(_schema_issues(proposal))
    issues.extend(_contradiction_issues(proposal, recent))
    issues.extend(_scope_issues(proposal))
    issues.extend(_rationale_issues(proposal))
    issues.extend(_turn_type_required_issues(proposal, require_turn_type=require_turn_type))
    issues.extend(icp_issues(proposal, icp))
    issues.extend(_finalizer_only_issues(proposal, finalizer_only=finalizer_only))
    issues.extend(_handoff_payload_issues(proposal))
    issues.extend(_terminate_payload_issues(proposal))

    if issues:
        logger.debug(
            "[SELF_CHECK] verdict=fail agent=%s kind=%s issues=%d",
            proposal.by_agent,
            proposal.kind,
            len(issues),
        )
        for issue in issues:
            logger.debug(
                "[SELF_CHECK] issue kind=%s detail=%s",
                issue.kind,
                issue.detail,
            )
        return SelfCheckRecord(verdict="fail", issues=issues)
    logger.debug(
        "[SELF_CHECK] verdict=pass agent=%s kind=%s",
        proposal.by_agent,
        proposal.kind,
    )
    return SelfCheckRecord(verdict="pass", issues=[])

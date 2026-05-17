"""Deterministic SELF_CHECK for Decision Cycle proposals."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from framework.memory.stores import DecisionEntry, Issue, MemoryStores, SelfCheckRecord

logger = logging.getLogger(__name__)

_PLANNER_ONLY_KINDS = frozenset({"plan_step", "terminate"})
_EXECUTOR_ONLY_KINDS = frozenset(
    {"code_edit", "tool_call", "reflection", "quality_failure"}
)
_SHARED_KINDS = frozenset({"handoff"})


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
    issues: list[Issue] = []
    window = recent[-10:]
    for entry in window:
        if entry.decision_id == proposal.decision_id:
            continue
        if entry.kind != proposal.kind:
            continue
        for key, value in proposal.payload.items():
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


def self_check(
    proposal: DecisionEntry,
    memory: MemoryStores,
    session_id: str,
) -> SelfCheckRecord:
    """Run schema, contradiction, scope, and rationale checks."""
    _ = session_id  # reserved for session-scoped rules in later phases
    recent = memory.decisions.get_last_n(proposal.session_id, 10)
    issues: list[Issue] = []
    issues.extend(_schema_issues(proposal))
    issues.extend(_contradiction_issues(proposal, recent))
    issues.extend(_scope_issues(proposal))
    issues.extend(_rationale_issues(proposal))

    if issues:
        logger.debug("self_check failed with %d issues", len(issues))
        return SelfCheckRecord(verdict="fail", issues=issues)
    return SelfCheckRecord(verdict="pass", issues=[])

"""Workflow state machine transitions (deterministic, no SLM)."""

from __future__ import annotations

import hashlib
import json
from typing import TypedDict

from framework.memory.stores import DecisionEntry, MemoryStores

STATE_PLAN = "PLAN"
STATE_DISPATCH = "DISPATCH"
STATE_EXECUTE = "EXECUTE"
STATE_EVALUATE = "EVALUATE"
STATE_REVISE = "REVISE"
STATE_DONE = "DONE"
STATE_ESCALATE = "ESCALATE"

# Alias for tests and routers
DONE = STATE_DONE


class WorkflowState(TypedDict, total=False):
    """LangGraph session state for the workflow FSM."""

    session_id: str
    goal: str
    hard_constraints: list[str]
    current_state: str
    active_subtask_id: str | None
    step_count: int
    retry_count: int
    loop_count: int
    max_steps: int
    max_retries: int
    last_evaluation: dict | None


def _decision_hash(entry: DecisionEntry) -> str:
    payload = json.dumps(entry.payload, sort_keys=True, default=str)
    digest = f"{entry.kind}:{payload}"
    return hashlib.sha256(digest.encode()).hexdigest()


def _loop_detected(memory: MemoryStores, state: WorkflowState) -> bool:
    """True when same kind+hash appears 3+ times in the last 5 decisions."""
    session_id = state.get("session_id", "")
    recent = memory.decisions.get_last_n(session_id, 5)
    counts: dict[str, int] = {}
    for entry in recent:
        key = _decision_hash(entry)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 3:
            return True
    return False


def next_state(state: WorkflowState, memory: MemoryStores) -> str:
    """Pure transition function; no SLM calls."""
    current = state.get("current_state", STATE_PLAN)
    retry_count = int(state.get("retry_count", 0))
    max_retries = int(state.get("max_retries", 3))

    if current == STATE_PLAN:
        return STATE_DISPATCH

    if current == STATE_REVISE:
        return STATE_EXECUTE

    if current == STATE_EVALUATE:
        if retry_count >= max_retries:
            return STATE_ESCALATE
        if _loop_detected(memory, state):
            return STATE_ESCALATE
        evaluation = state.get("last_evaluation") or {}
        if evaluation.get("passed") is True:
            return DONE
        if evaluation.get("passed") is False:
            return STATE_REVISE
        return STATE_DISPATCH

    if current == STATE_ESCALATE:
        return STATE_ESCALATE

    return STATE_DISPATCH

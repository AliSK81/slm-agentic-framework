"""Progress ledger built at EVALUATE."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from framework.control.workflow import WorkflowState, _loop_detected
from framework.memory.stores import MemoryStores, StateEntry


class ProgressLedger(BaseModel):
    """Snapshot of session progress for planner prompts."""

    session_id: str
    step_index: int
    is_task_satisfied: bool
    is_in_loop: bool
    is_progress_being_made: bool
    steps_consumed: int
    budget_remaining: int


def _tests_passed_count(status: dict) -> int:
    return int(status.get("passed", 0))


def build_progress_ledger(
    state: WorkflowState,
    memory: MemoryStores,
) -> ProgressLedger:
    """Build ledger from workflow state and memory; persist to State store."""
    session_id = state.get("session_id", "")
    step_count = int(state.get("step_count", 0))
    max_steps = int(state.get("max_steps", 20))
    evaluation = state.get("last_evaluation") or {}

    snapshots = memory.state.list_for_session(session_id)
    progress_made = True
    if len(snapshots) >= 2:
        prev = _tests_passed_count(snapshots[-2].tests_status)
        curr = _tests_passed_count(snapshots[-1].tests_status)
        progress_made = curr > prev

    ledger = ProgressLedger(
        session_id=session_id,
        step_index=step_count,
        is_task_satisfied=evaluation.get("passed") is True,
        is_in_loop=_loop_detected(memory, state),
        is_progress_being_made=progress_made,
        steps_consumed=step_count,
        budget_remaining=max(max_steps - step_count, 0),
    )

    memory.state.write(
        StateEntry(
            session_id=session_id,
            step_index=step_count,
            artifact_hash=f"ledger:{step_count}",
            tests_status={
                "passed": 1 if ledger.is_task_satisfied else 0,
                "failed": 0 if ledger.is_task_satisfied else 1,
                "errors": 0,
            },
            open_subtasks=[],
            timestamp=datetime.now(UTC),
        )
    )
    return ledger

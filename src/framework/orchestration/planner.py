"""Planner agent — plan and dispatch nodes."""

from __future__ import annotations

import logging
from typing import Any

from framework.control.cycle import DecisionCycle
from framework.control.workflow import STATE_DISPATCH, STATE_PLAN, WorkflowState
from framework.memory.stores import STORE_SUBTASKS, MemoryStores, SubTask
from framework.orchestration.messages import DispatchMessage, load_report, save_dispatch

logger = logging.getLogger(__name__)


class PlannerAgent:
    """Wraps Decision Cycle for planning and dispatching subtasks."""

    def __init__(self, cycle: DecisionCycle, memory: MemoryStores) -> None:
        self._cycle = cycle
        self._memory = memory

    def plan_node(self, state: WorkflowState) -> WorkflowState:
        """Decompose goal into subtasks via Decision Cycle."""
        session_id = state["session_id"]
        goal = state.get("goal", "")
        root_id = f"root:{session_id}"

        def action_fn(decision: Any) -> int:
            subtasks = decision.payload.get("subtasks", [])
            count = 0
            for raw in subtasks:
                task_id = raw.get("task_id") or f"st-{count}"
                self._memory.subtasks.register(
                    SubTask(
                        task_id=task_id,
                        parent_session_id=session_id,
                        description=raw.get("description", task_id),
                        status="open",
                        owner=raw.get("owner", "executor"),
                        depends_on=raw.get("depends_on", []),
                        result_ref=None,
                        attempt_count=0,
                    )
                )
                count += 1
            return count

        self._cycle.run(
            session_id,
            "planner",
            goal,
            root_id,
            action_fn=action_fn,
        )
        return {
            **state,
            "current_state": STATE_PLAN,
            "step_count": int(state.get("step_count", 0)) + 1,
        }

    def dispatch_node(self, state: WorkflowState) -> WorkflowState:
        """Select next open subtask and emit DispatchMessage."""
        session_id = state["session_id"]
        rows = self._memory.backend.query(
            STORE_SUBTASKS, {"parent_session_id": session_id}
        )
        pending: SubTask | None = None
        for row in rows:
            task = SubTask.model_validate(row)
            if task.task_id.startswith("root:"):
                continue
            if task.status == "open":
                pending = task
                break

        if pending is None:
            logger.info("No pending subtask for session %s", session_id)
            return {**state, "current_state": STATE_DISPATCH, "active_subtask_id": None}

        dispatch = DispatchMessage(
            session_id=session_id,
            task_id=pending.task_id,
            subtask_description=pending.description,
            memory_slice_keys=[],
            step_budget=int(state.get("max_steps", 20)),
            hard_constraints=list(state.get("hard_constraints", [])),
        )
        save_dispatch(self._memory.backend, dispatch)
        self._memory.subtasks.set_status(pending.task_id, "in_progress")

        return {
            **state,
            "current_state": STATE_DISPATCH,
            "active_subtask_id": pending.task_id,
            "step_count": int(state.get("step_count", 0)) + 1,
        }

    def has_report(self, session_id: str) -> bool:
        """Return True when executor report is available."""
        return load_report(self._memory.backend, session_id) is not None

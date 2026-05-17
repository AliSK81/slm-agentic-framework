"""Executor agent — carries out dispatched subtasks."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from framework.control.cycle import DecisionCycle
from framework.control.workflow import STATE_EXECUTE, WorkflowState
from framework.memory.stores import DecisionEntry, MemoryStores
from framework.orchestration.messages import (
    HandbackMessage,
    ReportMessage,
    load_dispatch,
    save_handback,
    save_report,
)
from framework.tools.compile_check import py_compile_check
from framework.tools.file_tools import edit_file, write_file
from framework.tools.test_runner import run_tests

logger = logging.getLogger(__name__)


def _payload_text(payload: dict) -> str:
    """Extract file body text from common SLM payload shapes."""
    for key in ("new_string", "content", "code"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


class ExecutorAgent:
    """Wraps Decision Cycle for code edits and tool calls."""

    def __init__(
        self,
        cycle: DecisionCycle,
        memory: MemoryStores,
        workspace: Path,
    ) -> None:
        self._cycle = cycle
        self._memory = memory
        self._workspace = workspace.resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)
        self.last_handback: HandbackMessage | None = None
        self.last_tool_result: Any = None
        self.last_edit_result: Any = None

    def execute_node(self, state: WorkflowState) -> WorkflowState:
        """Run one executor cycle for the active dispatch."""
        session_id = state["session_id"]
        dispatch = load_dispatch(self._memory.backend, session_id)
        if dispatch is None:
            logger.warning("No dispatch for session %s", session_id)
            return {**state, "current_state": STATE_EXECUTE}

        subtask_id = dispatch.task_id
        description = dispatch.subtask_description
        self.last_handback = None
        self.last_tool_result = None
        self.last_edit_result = None

        def action_fn(decision: DecisionEntry) -> Any:
            if decision.kind == "tool_call":
                tool = decision.payload.get("tool", "")
                if tool == "pytest":
                    target = decision.payload.get("target", "tests/")
                    self.last_tool_result = run_tests(
                        target, self._workspace, timeout_s=30
                    )
                    return self.last_tool_result
                if tool in ("py_compile", "py_compile_check"):
                    target = decision.payload.get("path", decision.payload.get("code", ""))
                    self.last_tool_result = py_compile_check(str(target))
                    return self.last_tool_result
                if tool == "write_file":
                    self.last_edit_result = write_file(
                        decision.payload.get("file_path", "solution.py"),
                        decision.payload.get("content", ""),
                        self._workspace,
                    )
                    return self.last_edit_result
            if decision.kind == "code_edit":
                file_path = decision.payload.get("file_path", "solution.py")
                target = (self._workspace / file_path).resolve()
                body = _payload_text(decision.payload)
                old_string = decision.payload.get("old_string", "")
                if not target.is_file():
                    self.last_edit_result = write_file(
                        file_path, body, self._workspace
                    )
                elif old_string:
                    self.last_edit_result = edit_file(
                        file_path,
                        old_string,
                        decision.payload.get("new_string", body),
                        self._workspace,
                    )
                elif body:
                    original = target.read_text(encoding="utf-8")
                    if not original.strip():
                        target.unlink(missing_ok=True)
                        self.last_edit_result = write_file(
                            file_path, body, self._workspace
                        )
                    else:
                        self.last_edit_result = edit_file(
                            file_path, original, body, self._workspace
                        )
                else:
                    self.last_edit_result = edit_file(
                        file_path, old_string, "", self._workspace
                    )
                return self.last_edit_result
            if decision.kind == "handoff":
                handback = HandbackMessage(
                    session_id=session_id,
                    task_id=subtask_id,
                    reason=decision.rationale,
                    blocked_on=decision.payload.get("blocked_on", "scope"),
                )
                self.last_handback = handback
                save_handback(self._memory.backend, handback)
                return handback
            return None

        result = self._cycle.run(
            session_id,
            "executor",
            description,
            subtask_id,
            action_fn=action_fn,
        )

        passed = False
        if self.last_handback is not None:
            passed = False
        elif self.last_tool_result is not None and hasattr(self.last_tool_result, "passed"):
            passed = bool(self.last_tool_result.passed)
        elif self.last_edit_result is not None and hasattr(self.last_edit_result, "ok"):
            passed = bool(self.last_edit_result.ok)
        elif result.decision is not None and not result.exhausted:
            passed = True

        report = ReportMessage(
            session_id=session_id,
            task_id=subtask_id,
            outcome="success" if passed else "failure",
            new_memory_refs=[f"decision:{result.decision.decision_id}"] if result.decision else [],
            evidence_summary=result.decision.rationale if result.decision else "no decision",
        )
        save_report(self._memory.backend, report)

        if passed and self.last_handback is None:
            existing = self._memory.subtasks.get(subtask_id)
            if existing is not None and existing.status == "in_progress":
                self._memory.subtasks.set_status(subtask_id, "done")

        return {
            **state,
            "current_state": STATE_EXECUTE,
            "step_count": int(state.get("step_count", 0)) + 1,
            "last_evaluation": {"passed": passed},
        }

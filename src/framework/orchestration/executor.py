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
from framework.tools.code_sanitize import sanitize_python_source
from framework.tools.compile_check import CompileResult, py_compile_check
from framework.tools.file_tools import FileResult, edit_file, write_file
from framework.tools.test_runner import run_tests

logger = logging.getLogger(__name__)


def _payload_text(payload: dict) -> str:
    """Extract file body text from common SLM payload shapes."""
    for key in ("new_string", "content", "code"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return sanitize_python_source(value)
    return ""


def _resolve_file_path(payload: dict, default: str = "solution.py") -> str:
    """Resolve target path from alternate SLM payload keys."""
    for key in ("file_path", "filePath", "file", "path"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _resolve_old_string(payload: dict) -> str:
    """Read old_string from common SLM payload spellings."""
    for key in ("old_string", "oldString"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def _verify_python_file(file_path: str, workspace: Path) -> FileResult:
    """Run compile check on a workspace file; return FileResult for executor."""
    target = (workspace / file_path).resolve()
    if not target.is_file():
        return FileResult(ok=False, message=f"file not found after write: {file_path}")
    compile_result: CompileResult = py_compile_check(str(target))
    if compile_result.ok:
        return FileResult(ok=True, message="ok")
    return FileResult(ok=False, message="; ".join(compile_result.errors))


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
        self.last_edit_result: FileResult | None = None

    def _apply_code_edit(self, decision: DecisionEntry) -> FileResult:
        """Write or edit a Python file from a code_edit decision."""
        payload = decision.payload
        file_path = _resolve_file_path(payload)
        target = (self._workspace / file_path).resolve()
        body = _payload_text(payload)
        old_string = _resolve_old_string(payload)
        new_raw = payload.get("new_string", payload.get("newString", body))

        if not body and not old_string:
            return FileResult(ok=False, message="empty code_edit payload")

        if not target.is_file():
            result = write_file(file_path, body, self._workspace)
        elif old_string:
            new_body = sanitize_python_source(str(new_raw))
            result = edit_file(file_path, old_string, new_body, self._workspace)
        elif body:
            original = target.read_text(encoding="utf-8")
            if not original.strip():
                target.unlink(missing_ok=True)
                result = write_file(file_path, body, self._workspace)
            else:
                new_body = sanitize_python_source(str(new_raw))
                result = edit_file(file_path, original, new_body, self._workspace)
        else:
            result = edit_file(file_path, old_string, "", self._workspace)

        if not result.ok:
            return result
        if file_path.endswith(".py") or file_path.endswith(".pyw"):
            return _verify_python_file(file_path, self._workspace)
        return result

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
                    target = decision.payload.get(
                        "path", decision.payload.get("code", "")
                    )
                    self.last_tool_result = py_compile_check(str(target))
                    return self.last_tool_result
                if tool == "write_file":
                    file_path = _resolve_file_path(decision.payload)
                    content = sanitize_python_source(
                        str(decision.payload.get("content", ""))
                    )
                    self.last_edit_result = write_file(
                        file_path, content, self._workspace
                    )
                    if self.last_edit_result.ok:
                        self.last_edit_result = _verify_python_file(
                            file_path, self._workspace
                        )
                    return self.last_edit_result
            if decision.kind == "code_edit":
                self.last_edit_result = self._apply_code_edit(decision)
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

        last_error: str | None = None
        if int(state.get("retry_count", 0)) > 0:
            reflection = state.get("reflection_guidance")
            evaluation = state.get("last_evaluation") or {}
            if reflection:
                last_error = str(reflection)
            else:
                last_error = evaluation.get("error_message") or evaluation.get("error")

        result = self._cycle.run(
            session_id,
            "executor",
            description,
            subtask_id,
            action_fn=action_fn,
            last_error=last_error,
            session_retry_count=int(state.get("retry_count", 0)),
        )

        passed = False
        if self.last_handback is not None:
            passed = False
        elif self.last_tool_result is not None and hasattr(self.last_tool_result, "passed"):
            passed = bool(self.last_tool_result.passed)
        elif self.last_edit_result is not None:
            passed = bool(self.last_edit_result.ok)

        report = ReportMessage(
            session_id=session_id,
            task_id=subtask_id,
            outcome="success" if passed else "failure",
            new_memory_refs=[f"decision:{result.decision.decision_id}"] if result.decision else [],
            evidence_summary=result.decision.rationale if result.decision else "no decision",
        )
        save_report(self._memory.backend, report)

        evaluation: dict[str, Any] = {"passed": passed}
        if not passed:
            if self.last_edit_result is not None and not self.last_edit_result.ok:
                evaluation["error_message"] = self.last_edit_result.message
            elif self.last_tool_result is not None:
                err = getattr(self.last_tool_result, "error_message", None)
                if err:
                    evaluation["error_message"] = str(err)

        return {
            **state,
            "current_state": STATE_EXECUTE,
            "last_evaluation": evaluation,
        }

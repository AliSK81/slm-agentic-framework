"""Executor agent — carries out dispatched subtasks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from framework.control.cycle import DecisionCycle
from framework.control.models import user_message_from_payload
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
from framework.tools.file_tools import FileResult, edit_file, read_file, write_file
from framework.error_control.sandbox import safe_execute

WriteFileFn = Callable[[str, str, Path], FileResult]
EditFileFn = Callable[[str, str, str, Path], FileResult]
from framework.tools.test_runner import run_tests

logger = logging.getLogger(__name__)


def _payload_text(payload: dict) -> str:
    """Extract file body text from common SLM payload shapes."""
    for key in ("new_string", "content", "code"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return sanitize_python_source(value)
    return ""


_TOOL_ALIASES: dict[str, str] = {
    "exec": "shell",
    "run_command": "shell",
    "run_terminal_cmd": "shell",
}


def _resolve_tool_name(payload: dict) -> str:
    """Resolve tool name from alternate SLM payload keys."""
    for key in ("tool", "name", "function", "command"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            raw = value.strip().lower()
            return _TOOL_ALIASES.get(raw, raw)
    return ""


def _resolve_file_path(payload: dict, default: str = "solution.py") -> str:
    """Resolve target path from alternate SLM payload keys."""
    sources: list[dict] = [payload]
    for nested_key in ("arguments", "args", "params"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            sources.append(nested)
    for source in sources:
        for key in ("file_path", "filePath", "file", "path"):
            value = source.get(key)
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
        *,
        permission_check: Callable[[str, str], bool] | None = None,
        write_file_fn: WriteFileFn | None = None,
        edit_file_fn: EditFileFn | None = None,
        effect_sink: list[str] | None = None,
        interactive_read_only: bool = False,
    ) -> None:
        self._cycle = cycle
        self._memory = memory
        self._workspace = workspace.resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)
        self.last_handback: HandbackMessage | None = None
        self.last_tool_result: Any = None
        self.last_edit_result: FileResult | None = None
        self._permission_check = permission_check
        self._write_file = write_file_fn or write_file
        self._edit_file = edit_file_fn or edit_file
        self._effect_sink = effect_sink
        self.interactive_read_only = interactive_read_only

    def _record_effect(self, text: str) -> None:
        if self._effect_sink is not None and text.strip():
            self._effect_sink.append(text.strip())

    def _write_permitted(self, decision: DecisionEntry) -> bool:
        """Allow writes on interactive read-only turns only when turn_type is edit/build."""
        if not self.interactive_read_only:
            return True
        turn_type = str((decision.payload or {}).get("turn_type", "")).lower()
        return turn_type in ("edit", "build")

    def _require_permission(
        self,
        kind: str,
        detail: str,
        *,
        decision: DecisionEntry | None = None,
    ) -> FileResult | None:
        """Return a denial ``FileResult`` when the permission gate blocks the action."""
        if kind in ("write_file", "edit_file") and decision is not None:
            if self.interactive_read_only and not self._write_permitted(decision):
                return FileResult(ok=False, message="permission denied: read-only turn")
        if self._permission_check is None:
            return None
        if self._permission_check(kind, detail):
            return None
        return FileResult(ok=False, message=f"permission denied: {kind} {detail}")

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

        op_kind = "edit_file" if target.is_file() else "write_file"
        blocked = self._require_permission(op_kind, file_path, decision=decision)
        if blocked is not None:
            return blocked

        if not target.is_file():
            result = self._write_file(file_path, body, self._workspace)
        elif old_string:
            new_body = sanitize_python_source(str(new_raw))
            result = self._edit_file(file_path, old_string, new_body, self._workspace)
        elif body:
            original = target.read_text(encoding="utf-8")
            if not original.strip():
                target.unlink(missing_ok=True)
                result = self._write_file(file_path, body, self._workspace)
            else:
                new_body = sanitize_python_source(str(new_raw))
                result = self._edit_file(file_path, original, new_body, self._workspace)
        else:
            result = self._edit_file(file_path, old_string, "", self._workspace)

        if not result.ok:
            return result
        self._record_effect(f"changed {file_path}")
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
            logger.debug(
                "[EXECUTOR] dispatch kind=%s turn_type=%s",
                decision.kind,
                (decision.payload or {}).get("turn_type"),
            )
            if decision.kind == "tool_call":
                tool = _resolve_tool_name(decision.payload)
                logger.debug("[EXECUTOR] tool_dispatch_start tool=%s", tool)
                if tool == "pytest":
                    target = decision.payload.get("target", "tests/")
                    blocked = self._require_permission("shell", f"pytest {target}")
                    if blocked is not None:
                        self.last_tool_result = blocked
                        return blocked
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
                    blocked = self._require_permission(
                        "write_file", file_path, decision=decision
                    )
                    if blocked is not None:
                        self.last_edit_result = blocked
                        return blocked
                    raw_content = str(decision.payload.get("content", ""))
                    if file_path.endswith((".py", ".pyw")):
                        raw_content = sanitize_python_source(raw_content)
                    self.last_edit_result = self._write_file(
                        file_path, raw_content, self._workspace
                    )
                    if self.last_edit_result.ok:
                        self._record_effect(f"created {file_path}")
                        if file_path.endswith((".py", ".pyw")):
                            self.last_edit_result = _verify_python_file(
                                file_path, self._workspace
                            )
                    return self.last_edit_result
                if tool == "read_file":
                    file_path = _resolve_file_path(decision.payload, default="")
                    if not file_path:
                        self.last_tool_result = FileResult(
                            ok=False, message="read_file requires path"
                        )
                        return self.last_tool_result
                    self.last_tool_result = read_file(file_path, self._workspace)
                    if self.last_tool_result.ok and self.last_tool_result.content:
                        self._record_effect(self.last_tool_result.content)
                    return self.last_tool_result
                if tool == "list_dir":
                    rel = _resolve_file_path(decision.payload, default=".")
                    target = (self._workspace / rel).resolve()
                    try:
                        target.relative_to(self._workspace)
                    except ValueError:
                        self.last_tool_result = FileResult(
                            ok=False, message="path outside workspace"
                        )
                        return self.last_tool_result
                    if not target.is_dir():
                        self.last_tool_result = FileResult(
                            ok=False, message=f"not a directory: {rel}"
                        )
                        return self.last_tool_result
                    names = sorted(
                        p.name + ("/" if p.is_dir() else "")
                        for p in target.iterdir()
                    )
                    listing = "\n".join(names)
                    self.last_tool_result = FileResult(
                        ok=True, message="ok", content=listing
                    )
                    self._record_effect(listing)
                    return self.last_tool_result
                if tool in ("shell", "run_command"):
                    command = str(decision.payload.get("command", "")).strip()
                    if not command:
                        self.last_tool_result = FileResult(
                            ok=False, message="shell requires command"
                        )
                        return self.last_tool_result
                    blocked = self._require_permission("shell", command)
                    if blocked is not None:
                        self.last_tool_result = blocked
                        return blocked
                    result = safe_execute(command, self._workspace, timeout_s=30)
                    self.last_tool_result = result
                    if result.stdout:
                        self._record_effect(result.stdout)
                    return result
            if decision.kind == "code_edit":
                file_path = _resolve_file_path(decision.payload)
                logger.debug("[EXECUTOR] code_edit file_path=%s", file_path)
                self.last_edit_result = self._apply_code_edit(decision)
                return self.last_edit_result
            if decision.kind == "terminate":
                answer = user_message_from_payload(
                    decision.payload,
                    fallback_rationale=decision.rationale,
                ).strip()
                logger.debug(
                    "[EXECUTOR] terminate user_message_len=%d turn_type=%s",
                    len(answer),
                    (decision.payload or {}).get("turn_type"),
                )
                self.last_tool_result = FileResult(
                    ok=bool(answer),
                    message="ok" if answer else "empty terminate answer",
                    content=answer or None,
                )
                if answer:
                    self._record_effect(answer)
                return self.last_tool_result
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
            evaluation = state.get("last_evaluation") or {}
            if state.get("interactive_mode"):
                cycle_error = state.get("cycle_last_error")
                if cycle_error:
                    last_error = str(cycle_error)
                else:
                    last_error = evaluation.get("error_message") or evaluation.get("error")
            else:
                reflection = state.get("reflection_guidance")
                if reflection:
                    last_error = str(reflection)
                else:
                    last_error = evaluation.get("error_message") or evaluation.get("error")

        require_turn_type = bool(
            state.get("interactive_mode") and not state.get("interactive_turn_bound")
        )
        turn_floor: int | None = None
        if state.get("interactive_mode"):
            turn_floor = int(state.get("decision_floor", 0))
        result = self._cycle.run(
            session_id,
            "executor",
            description,
            subtask_id,
            action_fn=action_fn,
            last_error=last_error,
            session_retry_count=int(state.get("retry_count", 0)),
            decision_floor=int(state.get("decision_floor", 0)),
            require_turn_type=require_turn_type,
            interactive_turn_floor=turn_floor,
        )

        passed = False
        if self.last_handback is not None:
            passed = False
        elif self.last_tool_result is not None and hasattr(self.last_tool_result, "passed"):
            passed = bool(self.last_tool_result.passed)
        elif self.last_tool_result is not None and hasattr(self.last_tool_result, "ok"):
            passed = bool(self.last_tool_result.ok)
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

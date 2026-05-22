"""Full session orchestration for e2e and smoke tests."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel

from framework.env import load_project_env

from framework.control.cycle import DecisionCycle
from framework.control.models import (
    ErrorControlBundle,
    is_needs_edit_handoff,
    is_needs_plan_handoff,
    is_needs_run_handoff,
    parse_terminate_payload,
)
from framework.orchestration.messages import DispatchMessage, save_dispatch
from framework.control.ledger import build_progress_ledger
from framework.control.workflow import (
    STATE_DONE,
    STATE_ESCALATE,
    STATE_EVALUATE,
    STATE_EXECUTE,
    STATE_PLAN,
    STATE_REVISE,
    WorkflowState,
    next_state,
)
from framework.memory.checkpoint import save_checkpoint
from framework.memory.reflection import _reflection_config, write_reflection
from framework.memory.stores import DecisionEntry, MemoryStores, StateEntry, SubTask
from framework.control.interactive import (
    InteractiveCompletionState,
    apply_compound_phase_promotion,
    bind_interactive_turn,
    compound_phase_for_turn_type,
    icp_after_successful_edit,
    icp_after_successful_tool,
    icp_initial_state,
    load_interactive_finalizer_enabled,
    tool_path_key,
    turn_type_from_payload,
)
from framework.memory.tool_results import append_tool_result
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.control.ablation import AblationSettings
from framework.slm.config import ModelProfile
from framework.orchestration.executor import (
    EditFileFn,
    ExecutorAgent,
    WriteFileFn,
    _resolve_tool_name,
)
from framework.orchestration.planner import PlannerAgent
from framework.orchestration.verify import Verifier, resolve_verifier
from framework.slm.client import SLMClient
from framework.slm.usage import SLMUsageAccumulator, TrackingSLMClient
from framework.slm.config import (
    active_provider_name,
    api_key_env_var_for_active_provider,
    api_key_for_active_provider,
    api_key_required_for_active_provider,
)
from framework.slm.registry import client_for_role, probe_client
from framework.tools.test_runner import run_tests

EngineName = Literal["loop", "graph"]

load_project_env()
logger = logging.getLogger(__name__)

_INTERACTIVE_NEEDS_PLAN = "NEEDS_PLAN"

class SessionOutcome(BaseModel):
    """Result of a full planner/executor session."""

    session_id: str
    outcome: Literal["solved", "max_steps_reached", "unresolvable", "escalate"] = (
        "max_steps_reached"
    )
    final_state: str = STATE_PLAN
    decision_count: int = 0
    step_count: int = 0
    retry_count: int = 0
    state_snapshot_count: int = 0
    checkpoint_path: str | None = None
    test_passed: bool = False
    error: str | None = None
    tokens_total: int = 0
    latency_ms_total: int = 0
    llm_calls: int = 0
    model_id: str = ""
    user_message: str = ""
    build_promoted: bool = False


def _session_user_message_from_decisions(
    memory: MemoryStores,
    session_id: str,
    *,
    decision_floor: int = 0,
) -> str:
    """Return typed user_message from the last terminate decision in this turn."""
    from framework.control.models import user_message_from_payload

    entries = memory.decisions.list_for_session(session_id)
    for entry in reversed(entries[decision_floor:]):
        if entry.kind == "terminate":
            return user_message_from_payload(entry.payload)
    return ""


def _normalize_goal_file_ref(raw: str) -> str:
    """Strip quotes from a filename token extracted from a user goal."""
    return raw.strip().strip("\"'`")


def _read_tool_key(tool: str, payload: dict) -> str:
    """Stable key for deduplicating repeated read-only tool calls."""
    path = _normalize_goal_file_ref(
        str(payload.get("file_path") or payload.get("path") or "")
    )
    return f"{tool}:{path}" if path else tool


def _tool_result_text(tool_result: object | None) -> str:
    """Extract user-visible text from a file or subprocess tool result."""
    if tool_result is None:
        return ""
    content = getattr(tool_result, "content", None)
    if content is not None:
        return str(content)
    stdout = getattr(tool_result, "stdout", None)
    if stdout:
        return str(stdout)
    return ""


def _run_interactive_finalizer(
    *,
    executor: ExecutorAgent,
    memory: MemoryStores,
    session_id: str,
    state: WorkflowState,
    goal: str,
) -> str:
    """Run one terminate-only Decision Cycle seeded with [TOOL RESULTS] (FI-4)."""
    from framework.tools.file_tools import FileResult

    floor = int(state.get("decision_floor", 0))
    if not memory.tool_results.list_for_turn(session_id, floor):
        return ""

    turn_state = state.get("interactive_turn_state") or {}
    declared = str(turn_state.get("declared_type") or "inspect")
    description = (
        f"[FINALIZER] User goal: {goal}\n"
        "Summarize for the user using [TOOL RESULTS] only — do not invent file "
        "contents. Respond with terminate only."
        f' Include turn_type:{declared}.'
    )

    def action_fn(decision: DecisionEntry) -> Any:
        if decision.kind != "terminate":
            return None
        msg = parse_terminate_payload(decision.payload).user_message.strip()
        return FileResult(
            ok=bool(msg),
            message="ok" if msg else "empty terminate answer",
            content=msg or None,
        )

    logger.debug("[INTERACTIVE] finalizer_start session=%s floor=%d", session_id, floor)
    result = executor._cycle.run(  # noqa: SLF001
        session_id,
        "executor",
        description,
        "st-main",
        action_fn=action_fn,
        max_retries=1,
        decision_floor=floor,
        interactive_turn_floor=floor,
        icp=None,
        finalizer_only=True,
    )
    if result.exhausted or result.decision is None:
        logger.debug("[INTERACTIVE] finalizer_failed session=%s", session_id)
        return ""
    return _session_user_message_from_decisions(
        memory,
        session_id,
        decision_floor=floor,
    )


def require_slm_api_key() -> str:
    """Return API key for the active SLM provider or raise with a clear message."""
    if not api_key_required_for_active_provider():
        return ""
    var = api_key_env_var_for_active_provider()
    key = api_key_for_active_provider()
    if not key or key == "your_key_here":
        raise RuntimeError(
            f"{var} is not set. Add it to .env before running e2e tests."
        )
    return key


def ensure_slm_api_key_configured() -> None:
    """Verify the API key env var is present locally (no network probe).

    Use :func:`validate_slm_api_key` for connectivity checks.
    """
    if not api_key_required_for_active_provider():
        return
    var = api_key_env_var_for_active_provider()
    key = require_slm_api_key()
    if len(key.strip()) < 20:
        raise RuntimeError(f"{var} looks like a placeholder. Set a real key in .env.")


def require_openrouter_key() -> str:
    """Backward-compatible alias for :func:`require_slm_api_key`."""
    return require_slm_api_key()


class ProbeResult(BaseModel):
    """Outcome of the SLM connectivity probe."""

    ok: bool
    attempts: int
    error: str | None = None


class ProbeFailedError(RuntimeError):
    """Raised when the SLM probe fails after all retry attempts."""

    def __init__(self, result: ProbeResult) -> None:
        self.result = result
        provider = active_provider_name()
        message = (
            f"SLM API probe failed after {result.attempts} attempt(s) "
            f"(provider={provider}): {result.error}"
        )
        super().__init__(message)


_TRANSIENT_PROBE_ERRORS = frozenset(
    {
        "timeout",
        "http_error",
        "connection_error",
        "ssl_error",
    }
)


def _is_transient_probe_error(error: str | None) -> bool:
    """Return True when the probe error is worth retrying."""
    if not error:
        return False
    if error in _TRANSIENT_PROBE_ERRORS:
        return True
    if error.startswith("http_5"):
        return True
    lowered = error.lower()
    return "connection" in lowered or "ssl" in lowered


def _run_probe_call(client: Any) -> Any:
    """Execute one planner-role probe ping."""
    return client.call(
        [{"role": "user", "content": "ping"}],
        role="planner",
        json_mode=False,
    )


def validate_slm_api_key(max_attempts: int = 3, *, base_delay_s: float = 2.0) -> ProbeResult:
    """Probe the active SLM provider with retries on transient failures.

    Inputs:
        max_attempts: Maximum probe tries (default 3).
        base_delay_s: Base delay for exponential backoff between retries.

    Outputs:
        ProbeResult with ``ok=True`` on success.

    Side effects:
        Sleeps between retries; raises ProbeFailedError when exhausted;
        raises RuntimeError for missing or placeholder API keys (no retry).
    """
    if api_key_required_for_active_provider():
        var = api_key_env_var_for_active_provider()
        key = require_slm_api_key()
        if len(key.strip()) < 20:
            raise RuntimeError(f"{var} looks like a placeholder. Set a real key in .env.")

    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        client = probe_client()
        try:
            result = _run_probe_call(client)
        finally:
            client.close()

        if not result.error:
            return ProbeResult(ok=True, attempts=attempt, error=None)

        last_error = result.error
        if not _is_transient_probe_error(last_error):
            break

        if attempt < max_attempts:
            delay = base_delay_s * (2 ** (attempt - 1))
            logger.warning(
                "SLM probe transient error (%s); retry %s/%s in %.1fs",
                last_error,
                attempt,
                max_attempts,
                delay,
            )
            time.sleep(delay)

    failed = ProbeResult(ok=False, attempts=attempt, error=last_error)
    raise ProbeFailedError(failed)


def validate_openrouter_key() -> ProbeResult:
    """Backward-compatible alias for :func:`validate_slm_api_key`."""
    return validate_slm_api_key()


def _apply_session_usage(outcome: SessionOutcome, usage: SLMUsageAccumulator, model_id: str) -> None:
    """Copy accumulated SLM usage into a session outcome."""
    outcome.tokens_total = usage.tokens_total
    outcome.latency_ms_total = usage.latency_ms_total
    outcome.llm_calls = usage.llm_calls
    outcome.model_id = model_id


def effective_wm_profile(profile: ModelProfile, ablation: AblationSettings) -> ModelProfile:
    """Return profile with ablation WM ceiling override applied when set."""
    if ablation.wm_ceiling_override is None:
        return profile
    return profile.model_copy(
        update={"max_working_memory_tokens": ablation.wm_ceiling_override}
    )


def _build_agents(
    memory: MemoryStores,
    workspace: Path,
    ablation: AblationSettings,
    *,
    permission_check: Callable[[str, str], bool] | None = None,
    write_file_fn: WriteFileFn | None = None,
    edit_file_fn: EditFileFn | None = None,
    effect_sink: list[str] | None = None,
    interactive_read_only: bool = False,
) -> tuple[PlannerAgent, ExecutorAgent, SLMUsageAccumulator, str]:
    usage = SLMUsageAccumulator()
    planner_inner = client_for_role("planner")
    executor_inner = client_for_role("executor")
    primary_model_id = planner_inner.profile.model_id
    planner_slm = TrackingSLMClient(planner_inner, usage)
    executor_slm = TrackingSLMClient(executor_inner, usage)
    planner_wm_profile = effective_wm_profile(planner_slm.profile, ablation)
    executor_wm_profile = effective_wm_profile(executor_slm.profile, ablation)
    bundle = ErrorControlBundle()
    planner = PlannerAgent(
        DecisionCycle(
            planner_slm,
            memory,
            WorkingMemoryBuilder(
                memory, planner_wm_profile, enable_memory=ablation.memory
            ),
            bundle,
            planner_slm.profile,
            ablation=ablation,
        ),
        memory,
    )
    executor = ExecutorAgent(
        DecisionCycle(
            executor_slm,
            memory,
            WorkingMemoryBuilder(
                memory, executor_wm_profile, enable_memory=ablation.memory
            ),
            bundle,
            executor_slm.profile,
            ablation=ablation,
        ),
        memory,
        workspace,
        permission_check=permission_check,
        write_file_fn=write_file_fn,
        edit_file_fn=edit_file_fn,
        effect_sink=effect_sink,
        interactive_read_only=interactive_read_only,
    )
    return planner, executor, usage, primary_model_id


def _run_revise_reflection(
    state: WorkflowState,
    memory: MemoryStores,
    goal: str,
    planner_slm: SLMClient,
    settings: AblationSettings,
) -> WorkflowState:
    """On REVISE, write verbal reflection (error_control only) for the next attempt.

    Inputs:
        state: Current workflow state after a failed evaluation.
        memory: Session memory stores.
        goal: Session root goal text.
        planner_slm: Planner-role SLM client (single bounded call).
        settings: Ablation toggles; reflection runs only when ``error_control`` is on.

    Outputs:
        Updated state with ``reflection_guidance`` for the executor cycle.

    Side effects:
        Appends a DecisionEntry(kind=reflection) when under the per-subtask cap.
    """
    if not settings.error_control:
        return {**state, "reflection_guidance": None}

    if not planner_slm.profile.reflection_enabled:
        return {**state, "reflection_guidance": None}

    retry_count = int(state.get("retry_count", 0))
    threshold = int(_reflection_config().get("trigger_retry_threshold", 1))
    if retry_count < threshold:
        return {**state, "reflection_guidance": None}

    session_id = state["session_id"]
    subtask_id = state.get("active_subtask_id") or "st-main"
    evaluation = state.get("last_evaluation") or {}
    failure_reason = (
        evaluation.get("error_message")
        or evaluation.get("error")
        or "tests did not pass"
    )

    subtask_desc = subtask_id
    rows = memory.backend.query("subtasks", {"task_id": subtask_id})
    if rows:
        subtask_desc = str(rows[0].get("description", subtask_id))

    text = write_reflection(
        planner_slm,
        session_id,
        int(state.get("step_count", 0)),
        goal,
        subtask_desc,
        retry_count,
        str(failure_reason),
        memory,
        subtask_id=subtask_id,
    )

    updated: WorkflowState = {**state, "reflection_guidance": text or None}
    if text and isinstance(updated.get("last_evaluation"), dict):
        evaluation_copy = dict(updated["last_evaluation"])
        evaluation_copy["reflection_guidance"] = text
        updated["last_evaluation"] = evaluation_copy
    return updated


def _ensure_work_subtasks(memory: MemoryStores, session_id: str, goal: str) -> None:
    """Ensure at least one open executor subtask exists after planning."""
    rows = memory.backend.query("subtasks", {"parent_session_id": session_id})
    work = [r for r in rows if not str(r.get("task_id", "")).startswith("root:")]
    if work:
        return
    memory.subtasks.register(
        SubTask(
            task_id="st-main",
            parent_session_id=session_id,
            description=goal,
            status="open",
            owner="executor",
        )
    )


def evaluate_workspace(workspace: Path, test_code: str) -> dict:
    """Run provided assertion code against the solution module in workspace."""
    preferred = workspace / "solution.py"
    if preferred.is_file():
        module = preferred.stem
    else:
        py_files = sorted(
            p for p in workspace.glob("*.py") if not p.name.startswith("test_")
        )
        if not py_files:
            return {"passed": False, "error": "no solution file in workspace"}
        module = py_files[0].stem
    test_path = workspace / "test_session.py"
    indented = "\n    ".join(line for line in test_code.strip().splitlines())
    test_path.write_text(
        f"from {module} import *\n\n"
        f"def test_session_assertions():\n    {indented}\n",
        encoding="utf-8",
    )
    result = run_tests("test_session.py", workspace, timeout_s=60)
    return {
        "passed": result.passed,
        "failed_tests": result.failed_tests,
        "error_message": result.error_message,
        "exit_code": result.exit_code,
    }


def _last_executor_decision(
    memory: MemoryStores,
    session_id: str,
) -> DecisionEntry | None:
    """Return the most recent executor decision for a session."""
    for entry in reversed(memory.decisions.list_for_session(session_id)):
        if entry.by_agent == "executor":
            return entry
    return None


def _interactive_goal_text(goal: str, constraints: list[str]) -> str:
    """Return the user goal for the executor subtask (no automatic suffix)."""
    _ = constraints
    return goal


def _setup_interactive_dispatch(
    memory: MemoryStores,
    session_id: str,
    goal: str,
    constraints: list[str],
) -> None:
    """Register a single executor subtask and dispatch for interactive turns."""
    effective_goal = _interactive_goal_text(goal, constraints)
    _ensure_work_subtasks(memory, session_id, effective_goal)
    save_dispatch(
        memory.backend,
        DispatchMessage(
            session_id=session_id,
            task_id="st-main",
            subtask_description=effective_goal,
            step_budget=20,
            hard_constraints=constraints,
        ),
    )
    task = memory.subtasks.get("st-main")
    if task is not None and task.status == "open":
        memory.subtasks.set_status("st-main", "in_progress")


def _interactive_initial_state(
    session_id: str,
    goal: str,
    constraints: list[str],
    *,
    max_retries: int,
) -> WorkflowState:
    """Build workflow state for a single executor-first interactive turn."""
    from framework.control.interactive import declaring_interactive_turn_state

    turn_state = declaring_interactive_turn_state()
    return {
        "session_id": session_id,
        "goal": goal,
        "hard_constraints": constraints,
        "current_state": STATE_EXECUTE,
        "active_subtask_id": "st-main",
        "step_count": 0,
        "retry_count": 0,
        "loop_count": 0,
        "max_steps": turn_state.max_steps,
        "max_retries": max_retries,
        "last_evaluation": None,
        "reflection_guidance": None,
        "cycle_last_error": None,
        "planned": True,
        "interactive_mode": True,
        "interactive_turn_bound": False,
        "interactive_turn_state": turn_state.model_dump(),
        "icp_state": icp_initial_state().model_dump(),
        "compound_phase": "inspect",
        "phase_billable": 0,
        "phase_cycles": {},
        "verify_ran": False,
    }


def _apply_interactive_turn_binding(
    state: WorkflowState,
    decision: DecisionEntry | None,
    executor: ExecutorAgent,
) -> bool:
    """Bind budget and read-only from cycle-1 declared turn_type; return True when bound."""
    if state.get("interactive_turn_bound"):
        return True
    if decision is None:
        return False
    turn_type = turn_type_from_payload(decision.payload)
    if turn_type is None:
        return False
    bound = bind_interactive_turn(turn_type)
    state["interactive_turn_bound"] = True
    state["interactive_turn_state"] = bound.model_dump()
    state["compound_phase"] = compound_phase_for_turn_type(turn_type)
    state["phase_billable"] = 0
    state["phase_cycles"] = {}
    state["max_steps"] = bound.max_steps
    executor.interactive_read_only = bound.read_only
    logger.debug(
        "[INTERACTIVE] bound turn_type=%s phase=%s max_steps=%d read_only=%s",
        turn_type,
        state["compound_phase"],
        bound.max_steps,
        bound.read_only,
    )
    return True


def _total_interactive_steps(state: WorkflowState) -> int:
    """Sum of billable cycles across all compound phases in this turn."""
    cycles = state.get("phase_cycles") or {}
    total = sum(int(v) for v in cycles.values())
    return total + int(state.get("phase_billable", 0))


def _promote_handoff_phase(
    state: WorkflowState,
    executor: ExecutorAgent,
    *,
    target: str,
    read_only: bool,
) -> None:
    """Apply typed handoff promotion with a fresh per-phase budget."""
    apply_compound_phase_promotion(state, target=target)  # type: ignore[arg-type]
    executor.interactive_read_only = read_only
    if target == "edit":
        state["interactive_turn_state"] = bind_interactive_turn("edit").model_dump()


def _abandon_open_executor_subtasks(memory: MemoryStores, session_id: str) -> None:
    """Mark in-flight executor work abandoned before planner promotion."""
    rows = memory.backend.query("subtasks", {"parent_session_id": session_id})
    for row in rows:
        task_id = str(row.get("task_id", ""))
        if task_id.startswith("root:"):
            continue
        if row.get("status") in ("open", "in_progress"):
            memory.subtasks.set_status(task_id, "abandoned")


def _goal_invites_build_promotion(goal: str) -> bool:
    """True when the user goal is plausibly a multi-file build (Python-only gate)."""
    lower = goal.strip().lower()
    hints = (
        "multi-file",
        "multifile",
        "multiple files",
        "several files",
        "scaffold",
        "refactor across",
        "large refactor",
        "full project",
        "build a ",
        "build the ",
        "across modules",
    )
    return any(h in lower for h in hints)


_READ_TOOLS = frozenset(
    {
        "read_file",
        "list_dir",
        "glob",
        "py_compile",
        "py_compile_check",
        "pytest",
        "shell",
        "run_command",
    }
)


def _read_only_invalid_decision(decision: DecisionEntry) -> bool:
    """True when an executor decision must be corrected on read-only interactive turns."""
    payload = decision.payload or {}
    turn_type = str(payload.get("turn_type", "")).lower()
    if decision.kind == "code_edit":
        return turn_type not in ("edit", "build")
    if decision.kind == "tool_call":
        tool = _resolve_tool_name(payload)
        if tool in ("write_file", "edit_file"):
            return turn_type not in ("edit", "build")
        return tool not in _READ_TOOLS
    if decision.kind == "handoff":
        return not (
            is_needs_edit_handoff(decision)
            or is_needs_run_handoff(decision)
            or is_needs_plan_handoff(decision)
        )
    return False


def _run_interactive_executor_turn(
    *,
    goal: str,
    constraints: list[str],
    workspace: Path,
    memory: MemoryStores,
    executor: ExecutorAgent,
    verifier: Verifier,
    session_id: str,
    max_retries: int,
) -> SessionOutcome:
    """Run executor cycles until terminate, needs_plan, or cycle budget exhausted."""
    _setup_interactive_dispatch(memory, session_id, goal, constraints)
    state = _interactive_initial_state(
        session_id,
        _interactive_goal_text(goal, constraints),
        constraints,
        max_retries=max_retries,
    )
    state["decision_floor"] = len(memory.decisions.list_for_session(session_id))
    state["code_edits_done"] = []
    attempts = 0
    interactive_read_only = bool(executor.interactive_read_only)
    max_steps = int(state["max_steps"])
    max_attempts = max_steps + max_retries + 2
    decision: DecisionEntry | None = None
    while int(state.get("phase_billable", 0)) < max_steps and attempts < max_attempts:
        attempts += 1
        phase_billable = int(state.get("phase_billable", 0))
        before_count = len(memory.decisions.list_for_session(session_id))
        logger.debug(
            "[INTERACTIVE] attempt=%d phase=%s phase_billable=%d max_steps=%d goal=%r",
            attempts,
            state.get("compound_phase"),
            phase_billable,
            max_steps,
            goal,
        )
        executor.execute_node(state)
        after_count = len(memory.decisions.list_for_session(session_id))
        decision = _last_executor_decision(memory, session_id)
        if _apply_interactive_turn_binding(state, decision, executor):
            interactive_read_only = bool(executor.interactive_read_only)
            max_steps = int(state["max_steps"])
            max_attempts = max(max_steps + max_retries + 2, attempts + 1)
        if after_count == before_count:
            logger.debug(
                "[INTERACTIVE] no_decision_recorded attempt=%d guidance=terminate",
                attempts,
            )
            state["retry_count"] = int(state.get("retry_count", 0)) + 1
            state["cycle_last_error"] = (
                "respond with a valid JSON terminate decision including "
                "non-empty user_message and turn_type."
            )
            if int(state.get("retry_count", 0)) > max_retries:
                logger.debug(
                    "[INTERACTIVE] executor_cycle_exhausted attempt=%d retries=%d",
                    attempts,
                    max_retries,
                )
                break
            continue

        if decision is not None and decision.kind == "terminate":
            parsed = parse_terminate_payload(decision.payload)
            user_msg = parsed.user_message
            state["phase_billable"] = phase_billable + 1
            logger.debug(
                "[INTERACTIVE] terminate turn_type=%s user_message_len=%d steps=%d",
                parsed.turn_type,
                len(user_msg),
                _total_interactive_steps(state),
            )
            outcome = SessionOutcome(
                session_id=session_id, step_count=_total_interactive_steps(state)
            )
            outcome.user_message = user_msg
            if parsed.turn_type in ("edit", "build"):
                evaluation = verifier.evaluate(workspace).as_dict()
                outcome.test_passed = bool(evaluation.get("passed"))
            outcome.outcome = "solved" if user_msg else "unresolvable"
            outcome.final_state = STATE_DONE
            outcome.decision_count = len(memory.decisions.list_for_session(session_id))
            return outcome

        if decision is not None and is_needs_plan_handoff(decision):
            state["phase_billable"] = phase_billable + 1
            outcome = SessionOutcome(
                session_id=session_id, step_count=_total_interactive_steps(state)
            )
            outcome.final_state = _INTERACTIVE_NEEDS_PLAN
            outcome.decision_count = len(memory.decisions.list_for_session(session_id))
            return outcome

        if decision is not None and is_needs_edit_handoff(decision):
            logger.debug("[INTERACTIVE] handoff_promote needs_edit attempt=%d", attempts)
            _promote_handoff_phase(state, executor, target="edit", read_only=False)
            interactive_read_only = False
            max_steps = int(state["max_steps"])
            max_attempts = max(max_steps + max_retries + 2, attempts + 1)
            continue

        if decision is not None and is_needs_run_handoff(decision):
            logger.debug("[INTERACTIVE] handoff_promote needs_run attempt=%d", attempts)
            _promote_handoff_phase(state, executor, target="run", read_only=True)
            interactive_read_only = True
            max_steps = int(state["max_steps"])
            max_attempts = max(max_steps + max_retries + 2, attempts + 1)
            continue

        if (
            interactive_read_only
            and decision is not None
            and _read_only_invalid_decision(decision)
        ):
            logger.debug(
                "[INTERACTIVE] read_only_reject kind=%s turn_type=%s billable=%d",
                decision.kind,
                (decision.payload or {}).get("turn_type"),
                phase_billable + 1,
            )
            state["phase_billable"] = phase_billable + 1
            state["retry_count"] = int(state.get("retry_count", 0)) + 1
            if decision.kind == "code_edit":
                state["cycle_last_error"] = (
                    "To write files: code_edit must include payload turn_type:edit, "
                    "then terminate{user_message, turn_type:edit}."
                )
            elif decision.kind == "handoff":
                state["cycle_last_error"] = (
                    "handoff reason must be needs_edit, needs_run, or needs_plan."
                )
            else:
                state["cycle_last_error"] = (
                    "Use read_file/list_dir tools then terminate turn_type:inspect, "
                    "or terminate turn_type:answer for meta/runtime questions only."
                )
            continue

        if decision is None:
            if phase_billable < max_steps:
                state["retry_count"] = int(state.get("retry_count", 0)) + 1
                state["cycle_last_error"] = (
                    "respond with a valid JSON terminate decision including "
                    "non-empty user_message and turn_type."
                )
                continue
            break

        if decision.kind == "tool_call":
            payload = decision.payload or {}
            tool = _resolve_tool_name(payload)
            read_key = tool_path_key(tool, payload)
            state["phase_billable"] = phase_billable + 1
            if tool in ("pytest", "py_compile", "py_compile_check"):
                state["verify_ran"] = True
            tool_result = executor.last_tool_result
            turn_floor = int(state.get("decision_floor", 0))
            result_path = read_key or str(
                payload.get("file_path") or payload.get("path") or "."
            )
            result_text = _tool_result_text(tool_result)
            if tool_result is not None and not getattr(tool_result, "ok", False):
                message = str(getattr(tool_result, "message", "") or "tool failed")
                append_tool_result(
                    memory,
                    session_id=session_id,
                    turn_floor=turn_floor,
                    tool=tool,
                    path=result_path,
                    output=message,
                    ok=False,
                )
                state["retry_count"] = int(state.get("retry_count", 0)) + 1
                state["cycle_last_error"] = message
                continue
            if tool_result is not None and getattr(tool_result, "ok", False):
                state["last_tool_snapshot"] = {
                    "tool": tool,
                    "payload": dict(payload),
                    "text": result_text,
                    "ok": True,
                }
                append_tool_result(
                    memory,
                    session_id=session_id,
                    turn_floor=turn_floor,
                    tool=tool,
                    path=result_path,
                    output=result_text,
                    ok=True,
                )
                icp = InteractiveCompletionState.model_validate(
                    state.get("icp_state", {})
                )
                state["icp_state"] = icp_after_successful_tool(
                    icp, read_key
                ).model_dump()
                state["cycle_last_error"] = None
            continue

        if decision.kind == "code_edit":
            state["phase_billable"] = phase_billable + 1
            payload = decision.payload or {}
            turn_type = str(payload.get("turn_type", "")).lower()
            file_path = str(payload.get("file_path") or "")
            edits_done: list[str] = state.setdefault("code_edits_done", [])
            if file_path and file_path in edits_done:
                state["retry_count"] = int(state.get("retry_count", 0)) + 1
                state["cycle_last_error"] = (
                    f"{file_path} was already updated. "
                    "terminate{user_message, turn_type:edit} now."
                )
                continue
            if turn_type in ("edit", "build") and not _read_only_invalid_decision(decision):
                if file_path:
                    edits_done.append(file_path)
                turn_floor = int(state.get("decision_floor", 0))
                append_tool_result(
                    memory,
                    session_id=session_id,
                    turn_floor=turn_floor,
                    tool="code_edit",
                    path=file_path or "file",
                    output=f"applied edit to {file_path or 'file'}",
                    ok=True,
                )
                icp = InteractiveCompletionState.model_validate(
                    state.get("icp_state", {})
                )
                state["icp_state"] = icp_after_successful_edit(icp).model_dump()
                state["cycle_last_error"] = None
            continue

        state["phase_billable"] = phase_billable + 1
        break

    outcome = SessionOutcome(
        session_id=session_id, step_count=_total_interactive_steps(state)
    )
    evaluation = verifier.evaluate(workspace).as_dict()
    outcome.test_passed = bool(evaluation.get("passed"))
    floor = int(state.get("decision_floor", 0))
    outcome.user_message = _session_user_message_from_decisions(
        memory,
        session_id,
        decision_floor=floor,
    )
    if not outcome.user_message.strip():
        has_tool_results = bool(memory.tool_results.list_for_turn(session_id, floor))
        if has_tool_results and load_interactive_finalizer_enabled():
            finalized = _run_interactive_finalizer(
                executor=executor,
                memory=memory,
                session_id=session_id,
                state=state,
                goal=goal,
            )
            if finalized.strip():
                outcome.user_message = finalized
                outcome.step_count += 1
    if outcome.user_message.strip() and outcome.test_passed:
        outcome.outcome = "solved"
        outcome.final_state = STATE_DONE
    else:
        outcome.outcome = "unresolvable"
        outcome.final_state = STATE_EXECUTE
        if not outcome.user_message.strip():
            outcome.user_message = ""
            outcome.error = outcome.error or "missing user_message"
        else:
            outcome.error = evaluation.get("error_message") or evaluation.get("error")
    logger.debug(
        "[INTERACTIVE] done outcome=%s steps=%d user_message_len=%d error=%r",
        outcome.outcome,
        outcome.step_count,
        len(outcome.user_message or ""),
        outcome.error,
    )
    outcome.decision_count = len(memory.decisions.list_for_session(session_id))
    return outcome


def run_turn(
    goal: str,
    constraints: list[str],
    workspace: Path,
    *,
    memory: MemoryStores | None = None,
    max_steps: int | None = None,
    max_retries: int = 3,
    session_id: str | None = None,
    checkpoint_dir: Path | None = None,
    ablation: AblationSettings | None = None,
    on_decision_append: Callable[[DecisionEntry], None] | None = None,
    verifier: Verifier | None = None,
    probe: bool = True,
    permission_check: Callable[[str, str], bool] | None = None,
    write_file_fn: WriteFileFn | None = None,
    edit_file_fn: EditFileFn | None = None,
    effect_sink: list[str] | None = None,
    interactive_read_only: bool = True,
    build_max_steps: int = 15,
) -> SessionOutcome:
    """Run one interactive turn: executor-first, optional planner promotion.

    Cycle-1 ``turn_type`` binds ``max_steps`` and read-only mode (FI-1); caller
    ``max_steps`` is ignored. Terminates on ``terminate{user_message}``. Promotes
    to the full planner graph when the executor emits ``handoff{reason:"needs_plan"}``.
    """
    if probe:
        validate_slm_api_key()
    session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
    workspace = workspace.resolve()
    effective_verifier = resolve_verifier("", verifier)
    workspace.mkdir(parents=True, exist_ok=True)

    if memory is None:
        db_path = workspace.parent / "data" / f"{session_id}.db"
        memory = MemoryStores.sqlite(db_path, on_decision=on_decision_append)
    elif on_decision_append is not None:
        memory.decisions._on_append = on_decision_append  # noqa: SLF001

    memory.subtasks.register(
        SubTask(
            task_id=f"root:{session_id}",
            parent_session_id=session_id,
            description="session root",
            status="open",
            owner="planner",
            original_goal=goal,
            hard_constraints=constraints,
        )
    )

    settings = ablation or AblationSettings()
    planner, executor, usage, primary_model_id = _build_agents(
        memory,
        workspace,
        settings,
        permission_check=permission_check,
        write_file_fn=write_file_fn,
        edit_file_fn=edit_file_fn,
        effect_sink=effect_sink,
        interactive_read_only=interactive_read_only,
    )

    memory.state.write(
        StateEntry(
            session_id=session_id,
            step_index=0,
            artifact_hash="session:interactive",
            tests_status={"passed": 0, "failed": 0, "errors": 0},
            open_subtasks=[],
            timestamp=datetime.now(UTC),
        )
    )

    if max_steps is not None:
        logger.debug(
            "[INTERACTIVE] ignoring caller max_steps=%s; budget bound from turn_type",
            max_steps,
        )
    outcome = _run_interactive_executor_turn(
        goal=goal,
        constraints=constraints,
        workspace=workspace,
        memory=memory,
        executor=executor,
        verifier=effective_verifier,
        session_id=session_id,
        max_retries=max_retries,
    )

    if outcome.final_state == _INTERACTIVE_NEEDS_PLAN:
        _abandon_open_executor_subtasks(memory, session_id)
        promoted = _run_full_session_graph(
            goal=goal,
            constraints=constraints,
            workspace=workspace,
            memory=memory,
            planner=planner,
            executor=executor,
            settings=settings,
            session_id=session_id,
            max_steps=build_max_steps,
            max_retries=max_retries,
            checkpoint_dir=checkpoint_dir,
            planner_enabled=True,
            verifier=effective_verifier,
        )
        promoted.user_message = _session_user_message_from_decisions(memory, session_id)
        promoted.build_promoted = True
        _apply_session_usage(promoted, usage, primary_model_id)
        planner._cycle._slm.close()  # noqa: SLF001
        executor._cycle._slm.close()
        return promoted

    _apply_session_usage(outcome, usage, primary_model_id)
    planner._cycle._slm.close()  # noqa: SLF001
    executor._cycle._slm.close()
    return outcome


def run_full_session(
    goal: str,
    constraints: list[str],
    test_code: str = "",
    workspace: Path | None = None,
    *,
    memory: MemoryStores | None = None,
    max_steps: int = 15,
    max_retries: int = 3,
    session_id: str | None = None,
    checkpoint_dir: Path | None = None,
    ablation: AblationSettings | None = None,
    planner_enabled: bool = True,
    on_decision_append: Callable[[DecisionEntry], None] | None = None,
    engine: EngineName = "graph",
    verifier: Verifier | None = None,
    probe: bool = True,
    permission_check: Callable[[str, str], bool] | None = None,
    write_file_fn: WriteFileFn | None = None,
    edit_file_fn: EditFileFn | None = None,
    effect_sink: list[str] | None = None,
    interactive: bool = False,
) -> SessionOutcome:
    """Run PLAN → DISPATCH → EXECUTE until DONE, ESCALATE, or budget exhausted.

    ``engine='graph'`` (default) drives the LangGraph FSM with SqliteSaver; ``engine='loop'``
    uses the legacy imperative loop for parity testing.

    When ``interactive=True``, delegates to :func:`run_turn` (planner-optional product path).
    """
    if interactive:
        return run_turn(
            goal,
            constraints,
            workspace,  # type: ignore[arg-type]
            memory=memory,
            max_steps=max_steps,
            max_retries=max_retries,
            session_id=session_id,
            checkpoint_dir=checkpoint_dir,
            ablation=ablation,
            on_decision_append=on_decision_append,
            verifier=verifier,
            probe=probe,
            permission_check=permission_check,
            write_file_fn=write_file_fn,
            edit_file_fn=edit_file_fn,
            effect_sink=effect_sink,
            interactive_read_only=False,
        )
    if probe:
        validate_slm_api_key()  # raises ProbeFailedError before task loop on probe failure
    if workspace is None:
        raise ValueError("workspace is required")
    session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
    workspace = workspace.resolve()
    effective_verifier = resolve_verifier(test_code, verifier)
    workspace.mkdir(parents=True, exist_ok=True)

    if memory is None:
        db_path = workspace.parent / "data" / f"{session_id}.db"
        memory = MemoryStores.sqlite(db_path, on_decision=on_decision_append)
    elif on_decision_append is not None:
        memory.decisions._on_append = on_decision_append  # noqa: SLF001 — eval streaming hook

    memory.subtasks.register(
        SubTask(
            task_id=f"root:{session_id}",
            parent_session_id=session_id,
            description="session root",
            status="open",
            owner="planner",
            original_goal=goal,
            hard_constraints=constraints,
        )
    )

    settings = ablation or AblationSettings()
    planner, executor, usage, primary_model_id = _build_agents(
        memory,
        workspace,
        settings,
        permission_check=permission_check,
        write_file_fn=write_file_fn,
        edit_file_fn=edit_file_fn,
        effect_sink=effect_sink,
    )

    memory.state.write(
        StateEntry(
            session_id=session_id,
            step_index=0,
            artifact_hash="session:start",
            tests_status={"passed": 0, "failed": 0, "errors": 0},
            open_subtasks=[],
            timestamp=datetime.now(UTC),
        )
    )

    if engine == "graph":
        outcome = _run_full_session_graph(
            goal=goal,
            constraints=constraints,
            workspace=workspace,
            memory=memory,
            planner=planner,
            executor=executor,
            settings=settings,
            session_id=session_id,
            max_steps=max_steps,
            max_retries=max_retries,
            checkpoint_dir=checkpoint_dir,
            planner_enabled=planner_enabled,
            verifier=effective_verifier,
        )
    else:
        outcome = _run_full_session_loop(
            goal=goal,
            constraints=constraints,
            workspace=workspace,
            memory=memory,
            planner=planner,
            executor=executor,
            settings=settings,
            session_id=session_id,
            max_steps=max_steps,
            max_retries=max_retries,
            checkpoint_dir=checkpoint_dir,
            planner_enabled=planner_enabled,
            verifier=effective_verifier,
        )

    _apply_session_usage(outcome, usage, primary_model_id)
    outcome.user_message = _session_user_message_from_decisions(memory, session_id)
    planner._cycle._slm.close()  # noqa: SLF001 — release HTTP clients
    executor._cycle._slm.close()
    return outcome


def _langgraph_sqlite_path(
    session_id: str,
    workspace: Path,
    checkpoint_dir: Path | None,
) -> Path:
    """Path for LangGraph SqliteSaver checkpoints (separate from JSON checkpoints)."""
    if checkpoint_dir is not None:
        return checkpoint_dir / f"{session_id}_langgraph.sqlite"
    return workspace.parent / "langgraph" / f"{session_id}.sqlite"


def _run_full_session_graph(
    *,
    goal: str,
    constraints: list[str],
    workspace: Path,
    memory: MemoryStores,
    planner: PlannerAgent,
    executor: ExecutorAgent,
    settings: AblationSettings,
    session_id: str,
    max_steps: int,
    max_retries: int,
    checkpoint_dir: Path | None,
    planner_enabled: bool,
    verifier: Verifier,
) -> SessionOutcome:
    """Production path: LangGraph FSM with durable SQLite checkpointing."""
    from framework.orchestration.graph import SessionGraphDeps, run_session_graph

    initial: WorkflowState = {
        "session_id": session_id,
        "goal": goal,
        "hard_constraints": constraints,
        "current_state": STATE_PLAN,
        "active_subtask_id": None,
        "step_count": 0,
        "retry_count": 0,
        "loop_count": 0,
        "max_steps": max_steps,
        "max_retries": max_retries,
        "last_evaluation": None,
        "reflection_guidance": None,
        "planned": False,
    }
    deps = SessionGraphDeps(
        planner=planner,
        executor=executor,
        memory=memory,
        workspace=workspace,
        verifier=verifier,
        goal=goal,
        settings=settings,
        planner_enabled=planner_enabled,
    )
    sqlite_path = _langgraph_sqlite_path(session_id, workspace, checkpoint_dir)
    outcome = SessionOutcome(session_id=session_id)

    try:
        state = run_session_graph(
            deps,
            initial,
            sqlite_path=sqlite_path,
            recursion_limit=max(max_steps * 6, 24),
        )
        evaluation = state.get("last_evaluation") or {}
        outcome.test_passed = bool(evaluation.get("passed"))
        outcome.step_count = int(state.get("step_count", 0))
        outcome.retry_count = int(state.get("retry_count", 0))
        final = state.get("current_state", STATE_PLAN)
        outcome.final_state = final
        if outcome.test_passed or final == STATE_DONE:
            outcome.outcome = "solved"
            outcome.final_state = STATE_DONE
        elif final == STATE_ESCALATE:
            outcome.outcome = "escalate"
        elif int(state.get("step_count", 0)) >= max_steps:
            outcome.outcome = "max_steps_reached"
        else:
            outcome.outcome = "unresolvable"
    except Exception as exc:  # noqa: BLE001
        logger.exception("LangGraph session failed: %s", exc)
        outcome.outcome = "unresolvable"
        outcome.error = str(exc)
        state = initial

    outcome.decision_count = len(memory.decisions.list_for_session(session_id))
    outcome.state_snapshot_count = len(memory.state.list_for_session(session_id))
    try:
        ckpt = save_checkpoint(
            session_id,
            int(state.get("step_count", 0)),
            memory,
            checkpoint_dir=checkpoint_dir,
        )
        outcome.checkpoint_path = str(ckpt)
    except OSError as exc:
        logger.warning("Checkpoint save failed: %s", exc)
    return outcome


def _run_full_session_loop(
    *,
    goal: str,
    constraints: list[str],
    workspace: Path,
    memory: MemoryStores,
    planner: PlannerAgent,
    executor: ExecutorAgent,
    settings: AblationSettings,
    session_id: str,
    max_steps: int,
    max_retries: int,
    checkpoint_dir: Path | None,
    planner_enabled: bool,
    verifier: Verifier,
) -> SessionOutcome:
    """Legacy imperative loop (parity / fallback)."""
    state: WorkflowState = {
        "session_id": session_id,
        "goal": goal,
        "hard_constraints": constraints,
        "current_state": STATE_PLAN,
        "active_subtask_id": None,
        "step_count": 0,
        "retry_count": 0,
        "loop_count": 0,
        "max_steps": max_steps,
        "max_retries": max_retries,
        "last_evaluation": None,
        "reflection_guidance": None,
        "planned": False,
    }

    outcome: SessionOutcome = SessionOutcome(session_id=session_id)

    try:
        while int(state.get("step_count", 0)) < max_steps:
            if not state.get("planned"):
                if planner_enabled:
                    planner.plan_node(state)
                _ensure_work_subtasks(memory, session_id, goal)
                state["planned"] = True
                state["step_count"] = int(state.get("step_count", 0)) + 1
                state["current_state"] = STATE_PLAN
                continue

            if state.get("active_subtask_id") is None:
                state = planner.dispatch_node(state)
                if state.get("active_subtask_id") is None:
                    outcome.outcome = "unresolvable"
                    outcome.final_state = state.get("current_state", STATE_PLAN)
                    break
                continue

            state = executor.execute_node(state)
            evaluation = verifier.evaluate(workspace).as_dict()
            state["last_evaluation"] = evaluation
            outcome.test_passed = bool(evaluation.get("passed"))

            if evaluation.get("passed"):
                outcome.outcome = "solved"
                outcome.final_state = STATE_DONE
                build_progress_ledger(
                    {**state, "current_state": STATE_EVALUATE}, memory
                )
                break

            state["current_state"] = STATE_EVALUATE
            if settings.control:
                build_progress_ledger(state, memory)
                transition = next_state(state, memory)
            elif evaluation.get("passed"):
                transition = STATE_DONE
            elif int(state.get("retry_count", 0)) >= int(state.get("max_retries", 3)):
                transition = STATE_ESCALATE
            else:
                transition = STATE_REVISE
            state["step_count"] = int(state.get("step_count", 0)) + 1

            if transition == STATE_DONE:
                outcome.outcome = "solved"
                outcome.final_state = STATE_DONE
                break
            if transition == STATE_ESCALATE:
                outcome.outcome = "escalate"
                outcome.final_state = STATE_ESCALATE
                break
            if transition == STATE_REVISE:
                state["current_state"] = STATE_REVISE
                state["retry_count"] = int(state.get("retry_count", 0)) + 1
                state = _run_revise_reflection(
                    state,
                    memory,
                    goal,
                    planner._cycle._slm,
                    settings,
                )
                continue

            state["active_subtask_id"] = None

        if outcome.outcome == "max_steps_reached" and outcome.test_passed:
            outcome.outcome = "solved"
            outcome.final_state = STATE_DONE

    except Exception as exc:  # noqa: BLE001 — session must not crash e2e harness
        logger.exception("Session failed: %s", exc)
        outcome.outcome = "unresolvable"
        outcome.error = str(exc)

    outcome.decision_count = len(memory.decisions.list_for_session(session_id))
    outcome.step_count = int(state.get("step_count", 0))
    outcome.retry_count = int(state.get("retry_count", 0))
    outcome.state_snapshot_count = len(memory.state.list_for_session(session_id))

    try:
        ckpt = save_checkpoint(
            session_id,
            int(state.get("step_count", 0)),
            memory,
            checkpoint_dir=checkpoint_dir,
        )
        outcome.checkpoint_path = str(ckpt)
    except OSError as exc:
        logger.warning("Checkpoint save failed: %s", exc)

    outcome.final_state = state.get("current_state", outcome.final_state)
    return outcome

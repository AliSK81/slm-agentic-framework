"""Full session orchestration for e2e and smoke tests."""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any, Literal

EngineName = Literal["loop", "graph"]

from pydantic import BaseModel

from framework.env import load_project_env

from framework.control.cycle import DecisionCycle
from framework.control.models import ErrorControlBundle, is_needs_plan_handoff, parse_terminate_payload
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
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.control.ablation import AblationSettings
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


def _session_user_message_from_decisions(
    memory: MemoryStores,
    session_id: str,
) -> str:
    """Return typed user_message from the last terminate decision (benchmark may leave empty)."""
    from framework.control.models import parse_terminate_payload

    for entry in reversed(memory.decisions.list_for_session(session_id)):
        if entry.kind == "terminate":
            return parse_terminate_payload(entry.payload).user_message
    return ""


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
    bundle = ErrorControlBundle()
    planner = PlannerAgent(
        DecisionCycle(
            planner_slm,
            memory,
            WorkingMemoryBuilder(
                memory, planner_slm.profile, enable_memory=ablation.memory
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
                memory, executor_slm.profile, enable_memory=ablation.memory
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
    """Augment the executor subtask when Aviona self-knowledge constraints are present."""
    if any(c.startswith("[AVIONA] Self/meta") for c in constraints):
        return (
            f"{goal}\n"
            "Answer using the runtime facts in [CONSTRAINTS]; "
            "terminate immediately with turn_type answer."
        )
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
    max_steps: int,
    max_retries: int,
) -> WorkflowState:
    """Build workflow state for a single executor-first interactive turn."""
    return {
        "session_id": session_id,
        "goal": goal,
        "hard_constraints": constraints,
        "current_state": STATE_EXECUTE,
        "active_subtask_id": "st-main",
        "step_count": 0,
        "retry_count": 0,
        "loop_count": 0,
        "max_steps": max_steps,
        "max_retries": max_retries,
        "last_evaluation": None,
        "reflection_guidance": None,
        "planned": True,
    }


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
        "grep",
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
        return True
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
    max_steps: int,
    max_retries: int,
    interactive_read_only: bool = False,
) -> SessionOutcome:
    """Run executor cycles until terminate, needs_plan, or cycle budget exhausted."""
    _setup_interactive_dispatch(memory, session_id, goal, constraints)
    state = _interactive_initial_state(
        session_id,
        _interactive_goal_text(goal, constraints),
        constraints,
        max_steps=max_steps,
        max_retries=max_retries,
    )
    billable_cycles = 0
    attempts = 0
    max_attempts = max_steps + 3
    decision: DecisionEntry | None = None
    while billable_cycles < max_steps and attempts < max_attempts:
        attempts += 1
        before_count = len(memory.decisions.list_for_session(session_id))
        executor.execute_node(state)
        after_count = len(memory.decisions.list_for_session(session_id))
        decision = _last_executor_decision(memory, session_id)
        if after_count == before_count:
            state["retry_count"] = int(state.get("retry_count", 0)) + 1
            state["reflection_guidance"] = (
                "respond with a valid JSON terminate decision including "
                "non-empty user_message and turn_type."
            )
            continue

        if decision is not None and decision.kind == "terminate":
            parsed = parse_terminate_payload(decision.payload)
            user_msg = parsed.user_message
            outcome = SessionOutcome(session_id=session_id, step_count=billable_cycles + 1)
            outcome.user_message = user_msg
            if parsed.turn_type in ("edit", "build"):
                evaluation = verifier.evaluate(workspace).as_dict()
                outcome.test_passed = bool(evaluation.get("passed"))
            outcome.outcome = "solved" if user_msg else "unresolvable"
            outcome.final_state = STATE_DONE
            outcome.decision_count = len(memory.decisions.list_for_session(session_id))
            return outcome

        if decision is not None and is_needs_plan_handoff(decision):
            if not _goal_invites_build_promotion(goal):
                state["retry_count"] = int(state.get("retry_count", 0)) + 1
                state["reflection_guidance"] = (
                    "handoff needs_plan is only for multi-file build tasks. "
                    "Use terminate{user_message, turn_type:answer|inspect|edit} "
                    "for this goal."
                )
                continue
            outcome = SessionOutcome(session_id=session_id, step_count=billable_cycles + 1)
            outcome.final_state = _INTERACTIVE_NEEDS_PLAN
            outcome.decision_count = len(memory.decisions.list_for_session(session_id))
            return outcome

        if (
            interactive_read_only
            and decision is not None
            and _read_only_invalid_decision(decision)
        ):
            state["retry_count"] = int(state.get("retry_count", 0)) + 1
            state["reflection_guidance"] = (
                "read-only turn: answer with terminate{user_message, turn_type:answer|inspect} "
                "using runtime: facts — do not use handoff, custom tools, or write tools."
            )
            continue

        if decision is None:
            if billable_cycles < max_steps:
                state["retry_count"] = int(state.get("retry_count", 0)) + 1
                state["reflection_guidance"] = (
                    "respond with a valid JSON terminate decision including "
                    "non-empty user_message and turn_type."
                )
                continue
            break

        billable_cycles += 1

        if decision is not None and decision.kind in ("tool_call", "code_edit"):
            continue

        break

    outcome = SessionOutcome(session_id=session_id, step_count=billable_cycles)
    evaluation = verifier.evaluate(workspace).as_dict()
    outcome.test_passed = bool(evaluation.get("passed"))
    outcome.user_message = _session_user_message_from_decisions(memory, session_id)
    if outcome.user_message.strip() and outcome.test_passed:
        outcome.outcome = "solved"
        outcome.final_state = STATE_DONE
    else:
        outcome.outcome = "unresolvable"
        outcome.final_state = STATE_EXECUTE
        if not outcome.user_message.strip():
            outcome.error = outcome.error or "missing user_message"
        else:
            outcome.error = evaluation.get("error_message") or evaluation.get("error")
    outcome.decision_count = len(memory.decisions.list_for_session(session_id))
    return outcome


def run_turn(
    goal: str,
    constraints: list[str],
    workspace: Path,
    *,
    memory: MemoryStores | None = None,
    max_steps: int = 6,
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
    interactive_read_only: bool = False,
    build_max_steps: int = 15,
) -> SessionOutcome:
    """Run one interactive turn: executor-first, optional planner promotion.

    Defaults to a single executor Decision Cycle. Terminates immediately on
    ``terminate{user_message}``. Promotes to the full planner graph when the
    executor emits ``handoff{reason:"needs_plan"}`` (Python transition only).
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

    outcome = _run_interactive_executor_turn(
        goal=goal,
        constraints=constraints,
        workspace=workspace,
        memory=memory,
        executor=executor,
        verifier=effective_verifier,
        session_id=session_id,
        max_steps=max_steps,
        max_retries=max_retries,
        interactive_read_only=interactive_read_only,
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

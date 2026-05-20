"""Full session orchestration for e2e and smoke tests."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from framework.env import load_project_env

from framework.control.cycle import DecisionCycle
from framework.control.models import ErrorControlBundle
from framework.control.ledger import build_progress_ledger
from framework.control.workflow import (
    STATE_DONE,
    STATE_ESCALATE,
    STATE_EVALUATE,
    STATE_PLAN,
    STATE_REVISE,
    WorkflowState,
    next_state,
)
from framework.memory.checkpoint import save_checkpoint
from framework.memory.stores import MemoryStores, StateEntry, SubTask
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.control.ablation import AblationSettings
from framework.orchestration.executor import ExecutorAgent
from framework.orchestration.planner import PlannerAgent
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


def validate_slm_api_key() -> None:
    """Raise if the API key is missing, placeholder, or rejected by the provider."""
    if api_key_required_for_active_provider():
        var = api_key_env_var_for_active_provider()
        key = require_slm_api_key()
        if len(key.strip()) < 20:
            raise RuntimeError(f"{var} looks like a placeholder. Set a real key in .env.")

    client = probe_client()
    try:
        result = client.call(
            [{"role": "user", "content": "ping"}],
            role="planner",
            json_mode=False,
        )
    finally:
        client.close()

    if result.error:
        provider = active_provider_name()
        raise RuntimeError(f"SLM API probe failed (provider={provider}): {result.error}")


def validate_openrouter_key() -> None:
    """Backward-compatible alias for :func:`validate_slm_api_key`."""
    validate_slm_api_key()


def _build_agents(
    memory: MemoryStores,
    workspace: Path,
    ablation: AblationSettings,
) -> tuple[PlannerAgent, ExecutorAgent]:
    planner_slm = client_for_role("planner")
    executor_slm = client_for_role("executor")
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
    )
    return planner, executor


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


def run_full_session(
    goal: str,
    constraints: list[str],
    test_code: str,
    workspace: Path,
    *,
    memory: MemoryStores | None = None,
    max_steps: int = 15,
    max_retries: int = 3,
    session_id: str | None = None,
    checkpoint_dir: Path | None = None,
    ablation: AblationSettings | None = None,
    planner_enabled: bool = True,
) -> SessionOutcome:
    """Run PLAN → DISPATCH → EXECUTE loop until DONE, ESCALATE, or budget exhausted."""
    validate_slm_api_key()
    session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    if memory is None:
        db_path = workspace.parent / "data" / f"{session_id}.db"
        memory = MemoryStores.sqlite(db_path)

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
    planner, executor = _build_agents(memory, workspace, settings)
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
    }

    outcome: SessionOutcome = SessionOutcome(session_id=session_id)
    planned = False

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

    try:
        while int(state.get("step_count", 0)) < max_steps:
            if not planned:
                if planner_enabled:
                    planner.plan_node(state)
                _ensure_work_subtasks(memory, session_id, goal)
                planned = True
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
            evaluation = evaluate_workspace(workspace, test_code)
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

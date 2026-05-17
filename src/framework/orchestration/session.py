"""Full session orchestration for e2e and smoke tests."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
import yaml
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
from framework.orchestration.executor import ExecutorAgent
from framework.orchestration.planner import PlannerAgent
from framework.slm.client import SLMClient
from framework.tools.test_runner import run_tests

load_project_env()
logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MODELS_CONFIG = _PROJECT_ROOT / "configs" / "models.yaml"


class SessionOutcome(BaseModel):
    """Result of a full planner/executor session."""

    session_id: str
    outcome: Literal["solved", "max_steps_reached", "unresolvable", "escalate"] = (
        "max_steps_reached"
    )
    final_state: str = STATE_PLAN
    decision_count: int = 0
    state_snapshot_count: int = 0
    checkpoint_path: str | None = None
    test_passed: bool = False
    error: str | None = None


def require_openrouter_key() -> str:
    """Return API key or raise with a clear message."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key or key.strip() == "your_key_here":
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env before running e2e tests."
        )
    return key


def validate_openrouter_key() -> None:
    """Raise if the API key is missing, placeholder, or rejected by OpenRouter."""
    key = require_openrouter_key()
    if len(key.strip()) < 20:
        raise RuntimeError(
            "OPENROUTER_API_KEY looks like a placeholder. Set a real key in .env."
        )

    base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    raw = yaml.safe_load(_MODELS_CONFIG.read_text(encoding="utf-8"))
    profiles: dict = raw.get("profiles", {})
    planner_profile = profiles.get("qwen2.5-coder-7b-instruct", {})
    probe_model = os.getenv(
        "OPENROUTER_PROBE_MODEL",
        planner_profile.get("openrouter_id", "mistralai/devstral-small"),
    )
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "thesis-framework",
        "X-Title": "SLM-Thesis",
        "Content-Type": "application/json",
    }
    payload = {
        "model": probe_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        response = httpx.post(
            f"{base}/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"OpenRouter auth check failed: {exc}") from exc
    if response.status_code == 401:
        raise RuntimeError(
            "OPENROUTER_API_KEY rejected (401). Update .env with a valid key."
        )
    if response.status_code >= 400:
        raise RuntimeError(
            f"OpenRouter auth check failed: HTTP {response.status_code}"
        )


def _profile_name_for_role(role: str) -> str:
    raw = yaml.safe_load(_MODELS_CONFIG.read_text(encoding="utf-8"))
    profiles: dict = raw.get("profiles", {})
    env_key = "PLANNER_MODEL" if role == "planner" else "EXECUTOR_MODEL"
    target_id = os.getenv(env_key, "")
    for name, cfg in profiles.items():
        if cfg.get("openrouter_id") == target_id:
            return name
    return "qwen2.5-coder-7b-instruct" if role == "planner" else "devstral-small"


def _build_agents(
    memory: MemoryStores,
    workspace: Path,
) -> tuple[PlannerAgent, ExecutorAgent]:
    planner_slm = SLMClient(_profile_name_for_role("planner"))
    executor_slm = SLMClient(_profile_name_for_role("executor"))
    bundle = ErrorControlBundle()
    planner = PlannerAgent(
        DecisionCycle(
            planner_slm,
            memory,
            WorkingMemoryBuilder(memory, planner_slm.profile),
            bundle,
            planner_slm.profile,
        ),
        memory,
    )
    executor = ExecutorAgent(
        DecisionCycle(
            executor_slm,
            memory,
            WorkingMemoryBuilder(memory, executor_slm.profile),
            bundle,
            executor_slm.profile,
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
    """Run provided assertion code against the first solution module in workspace."""
    py_files = [
        p
        for p in workspace.glob("*.py")
        if not p.name.startswith("test_")
    ]
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
) -> SessionOutcome:
    """Run PLAN → DISPATCH → EXECUTE loop until DONE, ESCALATE, or budget exhausted."""
    validate_openrouter_key()
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

    planner, executor = _build_agents(memory, workspace)
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
            build_progress_ledger(state, memory)
            transition = next_state(state, memory)
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

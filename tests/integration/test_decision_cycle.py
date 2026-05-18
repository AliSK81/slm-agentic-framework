"""Decision Cycle integration tests with mocked SLM."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework.control.cycle import DecisionCycle
from framework.control.models import ErrorControlBundle
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import DecisionEntry, MemoryStores, SubTask
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
    """Queue-based SLM stub for cycle tests."""

    def __init__(
        self,
        responses: list[str],
        profile: ModelProfile | None = None,
    ) -> None:
        self._responses = list(responses)
        self.profile = profile or ModelProfile(
            model_id="mock",
            context_limit=4096,
            effective_context=4096,
            max_working_memory_tokens=650,
            tool_output_caps={},
            skill_budget_tokens=120,
            timeout_by_role={"planner": 60, "executor": 75},
        )

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        _ = messages, role, json_mode
        if not self._responses:
            return SLMResponse(error="empty_queue", model="mock")
        content = self._responses.pop(0)
        return SLMResponse(content=content, model="mock", tokens_used=1, elapsed_ms=1)


def _valid_executor_json() -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "payload": {"tool": "pytest"},
            "rationale": "Run tests for the subtask.",
            "references": [],
        }
    )


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "cycle.db"))


@pytest.fixture
def session_setup(memory: MemoryStores) -> str:
    session_id = "sess-cycle"
    memory.subtasks.register(
        SubTask(
            task_id=f"root:{session_id}",
            parent_session_id=session_id,
            description="root",
            status="open",
            owner="planner",
            original_goal="Build feature X",
            hard_constraints=["No external network"],
        )
    )
    return session_id


def _cycle(
    slm: MockSLMClient,
    memory: MemoryStores,
    *,
    max_steps: int = 20,
) -> DecisionCycle:
    profile = slm.profile
    builder = WorkingMemoryBuilder(memory, profile)
    return DecisionCycle(
        slm,
        memory,
        builder,
        ErrorControlBundle(),
        profile,
        max_steps=max_steps,
    )


def test_cycle_completes_on_valid_proposal(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """Mocked SLM returns valid JSON → cycle completes, decision recorded."""
    slm = MockSLMClient([_valid_executor_json()])
    cycle = _cycle(slm, memory)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: {"ok": True},
    )
    assert not result.exhausted
    assert result.decision is not None
    assert result.outcome == {"ok": True}


def test_cycle_retries_on_schema_fail(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """Invalid JSON then valid → success after retry."""
    slm = MockSLMClient(["not-json", _valid_executor_json()])
    cycle = _cycle(slm, memory)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: "acted",
        max_retries=3,
    )
    assert not result.exhausted
    assert result.retry_count == 1
    assert result.decision is not None


def test_cycle_marks_exhausted_after_max_retries(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """SLM always invalid → exhausted after max_retries."""
    slm = MockSLMClient(["bad", "also-bad", "still-bad", "nope"])
    cycle = _cycle(slm, memory)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: None,
        max_retries=2,
    )
    assert result.exhausted


def test_cycle_records_decision_in_log(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """After successful cycle → DecisionLog has exactly 1 new entry."""
    slm = MockSLMClient([_valid_executor_json()])
    cycle = _cycle(slm, memory)
    before = len(memory.decisions.list_for_session(session_setup))
    cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: None,
    )
    after = len(memory.decisions.list_for_session(session_setup))
    assert after - before == 1


def test_cycle_records_self_check_result(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """DecisionEntry in log has self_check.verdict == 'pass'."""
    slm = MockSLMClient([_valid_executor_json()])
    cycle = _cycle(slm, memory)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: None,
    )
    assert result.decision is not None
    assert result.decision.self_check.verdict == "pass"
    logged = memory.decisions.get_last_n(session_setup, 1)[0]
    assert logged.self_check.verdict == "pass"


def test_budget_limiter_stops_cycle(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """max_steps=1, step_count=1 → budget_exceeded before calling SLM."""
    slm = MockSLMClient([_valid_executor_json()])
    cycle = _cycle(slm, memory, max_steps=1)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: None,
        step_count=1,
        max_steps=1,
    )
    assert result.budget_exceeded
    assert slm._responses  # SLM never called


def _planner_plan_json() -> str:
    return json.dumps(
        {
            "kind": "plan_step",
            "rationale": "Decompose into one implementation step.",
            "payload": {
                "subtasks": [
                    {
                        "task_id": "st-impl",
                        "description": "Implement the feature",
                        "owner": "executor",
                    }
                ]
            },
            "references": [],
        }
    )


def _agents(
    slm: MockSLMClient,
    memory: MemoryStores,
    workspace: Path,
) -> tuple:
    from framework.orchestration.executor import ExecutorAgent
    from framework.orchestration.planner import PlannerAgent

    cycle = _cycle(slm, memory)
    planner = PlannerAgent(cycle, memory)
    executor = ExecutorAgent(cycle, memory, workspace)
    return planner, executor


def _workflow_state(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "goal": "Build feature X",
        "hard_constraints": ["No external network"],
        "current_state": "PLAN",
        "active_subtask_id": None,
        "step_count": 0,
        "retry_count": 0,
        "loop_count": 0,
        "max_steps": 10,
        "max_retries": 3,
        "last_evaluation": None,
    }


def test_planner_writes_subtasks_to_registry(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    slm = MockSLMClient([_planner_plan_json()])
    planner, _ = _agents(slm, memory, Path("."))
    state = _workflow_state(session_setup)
    planner.plan_node(state)
    tasks = [
        t
        for t in memory.backend.query("subtasks", {"parent_session_id": session_setup})
        if not t["task_id"].startswith("root:")
    ]
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "st-impl"


def test_planner_dispatch_selects_pending_subtask(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    memory.subtasks.register(
        SubTask(
            task_id="st-pending",
            parent_session_id=session_setup,
            description="Do work",
            status="open",
            owner="executor",
        )
    )
    slm = MockSLMClient([])
    planner, _ = _agents(slm, memory, Path("."))
    updated = planner.dispatch_node(_workflow_state(session_setup))
    assert updated["active_subtask_id"] == "st-pending"
    task = memory.subtasks.get("st-pending")
    assert task is not None
    assert task.status == "in_progress"


def test_executor_calls_tool_on_tool_call_decision(
    memory: MemoryStores,
    session_setup: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from framework.orchestration.messages import save_dispatch, DispatchMessage
    from framework.tools.test_runner import TestResult

    save_dispatch(
        memory.backend,
        DispatchMessage(
            session_id=session_setup,
            task_id="st-tool",
            subtask_description="run tests",
            step_budget=5,
            hard_constraints=[],
        ),
    )
    calls: list[str] = []

    def fake_run_tests(target: str, workspace: Path, timeout_s: int = 30) -> TestResult:
        _ = workspace, timeout_s
        calls.append(target)
        return TestResult(passed=True, total_tests=1, exit_code=0, duration_ms=1)

    monkeypatch.setattr(
        "framework.orchestration.executor.run_tests",
        fake_run_tests,
    )
    slm = MockSLMClient([_valid_executor_json()])
    _, executor = _agents(slm, memory, tmp_path)
    state = _workflow_state(session_setup)
    state["active_subtask_id"] = "st-tool"
    executor.execute_node(state)
    assert calls == ["tests/"]


def test_executor_calls_edit_file_on_code_edit(
    memory: MemoryStores,
    session_setup: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from framework.orchestration.messages import DispatchMessage, save_dispatch
    from framework.tools.file_tools import FileResult

    target = tmp_path / "module.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")
    save_dispatch(
        memory.backend,
        DispatchMessage(
            session_id=session_setup,
            task_id="st-edit",
            subtask_description="edit module",
            step_budget=5,
            hard_constraints=[],
        ),
    )
    edits: list[tuple[str, str, str]] = []

    def fake_edit(
        file_path: str,
        old_string: str,
        new_string: str,
        workspace: Path,
    ) -> FileResult:
        edits.append((file_path, old_string, new_string))
        return FileResult(ok=True, message="updated")

    monkeypatch.setattr(
        "framework.orchestration.executor.edit_file",
        fake_edit,
    )
    slm = MockSLMClient(
        [
            json.dumps(
                {
                    "kind": "code_edit",
                    "payload": {
                        "file_path": "module.py",
                        "old_string": "return 1",
                        "new_string": "return 2",
                    },
                    "rationale": "fix return value",
                    "references": [],
                }
            )
        ]
    )
    _, executor = _agents(slm, memory, tmp_path)
    executor.execute_node(_workflow_state(session_setup))
    assert edits
    assert edits[0][0] == "module.py"


def test_executor_emits_handback_when_out_of_scope(
    memory: MemoryStores,
    session_setup: str,
    tmp_path: Path,
) -> None:
    from framework.orchestration.messages import DispatchMessage, load_handback, save_dispatch

    save_dispatch(
        memory.backend,
        DispatchMessage(
            session_id=session_setup,
            task_id="st-hand",
            subtask_description="blocked task",
            step_budget=5,
            hard_constraints=[],
        ),
    )
    slm = MockSLMClient(
        [
            json.dumps(
                {
                    "kind": "handoff",
                    "payload": {"blocked_on": "architecture"},
                    "rationale": "Need planner to replan",
                    "references": [],
                }
            )
        ]
    )
    _, executor = _agents(slm, memory, tmp_path)
    executor.execute_node(_workflow_state(session_setup))
    handback = load_handback(memory.backend, session_setup)
    assert handback is not None
    assert handback.blocked_on == "architecture"


def test_planner_receives_report_after_executor_done(
    memory: MemoryStores,
    session_setup: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from framework.orchestration.messages import DispatchMessage, save_dispatch
    from framework.tools.test_runner import TestResult

    save_dispatch(
        memory.backend,
        DispatchMessage(
            session_id=session_setup,
            task_id="st-report",
            subtask_description="run tests",
            step_budget=5,
            hard_constraints=[],
        ),
    )
    monkeypatch.setattr(
        "framework.orchestration.executor.run_tests",
        lambda *a, **k: TestResult(passed=True, total_tests=1, exit_code=0, duration_ms=1),
    )
    slm = MockSLMClient([_valid_executor_json()])
    planner, executor = _agents(slm, memory, tmp_path)
    executor.execute_node(_workflow_state(session_setup))
    assert planner.has_report(session_setup)

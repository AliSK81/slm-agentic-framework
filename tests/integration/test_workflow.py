"""Workflow FSM integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from framework.control.ledger import build_progress_ledger
from framework.control.workflow import (
    STATE_EVALUATE,
    STATE_PLAN,
    STATE_REVISE,
    WorkflowState,
    _loop_detected,
    next_state,
)
from framework.memory.backend import SQLiteBackend
from framework.memory.reflection import write_reflection
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord, SubTask
from framework.control.ablation import AblationSettings
from framework.orchestration.executor import ExecutorAgent
from framework.orchestration.graph import build_graph, sqlite_checkpointer
from framework.orchestration.session import ProbeResult, run_full_session
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
    """SLM stub returning fixed reflection text."""

    def __init__(self, content: str = "Try a smaller change next.") -> None:
        self._content = content
        self.profile = ModelProfile(
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
        return SLMResponse(content=self._content, model="mock", tokens_used=1, elapsed_ms=1)


def _self_check() -> SelfCheckRecord:
    return SelfCheckRecord(verdict="pass", issues=[])


def _base_state(**overrides: Any) -> WorkflowState:
    state: WorkflowState = {
        "session_id": "sess-wf",
        "goal": "Build X",
        "hard_constraints": ["no network"],
        "current_state": STATE_EVALUATE,
        "active_subtask_id": "t-1",
        "step_count": 2,
        "retry_count": 0,
        "loop_count": 0,
        "max_steps": 10,
        "max_retries": 3,
        "last_evaluation": None,
    }
    state.update(overrides)
    return state


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "workflow.db"))


def _append_decision(
    memory: MemoryStores,
    *,
    decision_id: str,
    kind: str = "tool_call",
    payload: dict | None = None,
) -> None:
    memory.decisions.append(
        DecisionEntry(
            session_id="sess-wf",
            decision_id=decision_id,
            step_index=0,
            by_agent="executor",
            kind=kind,  # type: ignore[arg-type]
            payload=payload or {"tool": "pytest"},
            rationale="r",
            references=[],
            self_check=_self_check(),
            timestamp=datetime.now(UTC),
        )
    )


def test_next_state_plan_returns_dispatch(memory: MemoryStores) -> None:
    state = _base_state(current_state=STATE_PLAN)
    assert next_state(state, memory) == "DISPATCH"


def test_next_state_evaluate_returns_done_when_tests_pass(memory: MemoryStores) -> None:
    state = _base_state(last_evaluation={"passed": True})
    assert next_state(state, memory) == "DONE"


def test_next_state_evaluate_returns_revise_on_test_failure(memory: MemoryStores) -> None:
    state = _base_state(last_evaluation={"passed": False})
    assert next_state(state, memory) == "REVISE"


def test_next_state_evaluate_returns_escalate_when_retries_exhausted(
    memory: MemoryStores,
) -> None:
    state = _base_state(retry_count=3, max_retries=3)
    assert next_state(state, memory) == "ESCALATE"


def test_next_state_revise_returns_execute(memory: MemoryStores) -> None:
    state = _base_state(current_state=STATE_REVISE)
    assert next_state(state, memory) == "EXECUTE"


def test_loop_detected_at_threshold_3(memory: MemoryStores) -> None:
    payload = {"tool": "pytest"}
    for idx in range(3):
        _append_decision(memory, decision_id=f"loop-{idx}", payload=payload)
    state = _base_state()
    assert _loop_detected(memory, state)


def test_loop_not_detected_below_threshold(memory: MemoryStores) -> None:
    for idx in range(2):
        _append_decision(memory, decision_id=f"noloop-{idx}", payload={"tool": "pytest"})
    state = _base_state()
    assert not _loop_detected(memory, state)


def test_progress_ledger_built_correctly(memory: MemoryStores) -> None:
    state = _base_state(last_evaluation={"passed": True}, step_count=3, max_steps=10)
    ledger = build_progress_ledger(state, memory)
    assert ledger.session_id == "sess-wf"
    assert ledger.step_index == 3
    assert ledger.is_task_satisfied is True
    assert ledger.steps_consumed == 3
    assert ledger.budget_remaining == 7


def test_graph_compiles_without_error(memory: MemoryStores) -> None:
    graph = build_graph(planner=object(), executor=object(), memory=memory)
    assert graph is not None


def test_graph_checkpoint_saves_state(memory: MemoryStores) -> None:
    graph = build_graph(planner=object(), executor=object(), memory=memory)
    initial: WorkflowState = {
        "session_id": "sess-ck",
        "goal": "g",
        "hard_constraints": [],
        "current_state": STATE_PLAN,
        "active_subtask_id": None,
        "step_count": 0,
        "retry_count": 0,
        "loop_count": 0,
        "max_steps": 5,
        "max_retries": 2,
        "last_evaluation": {"passed": True},
    }
    run_config = {"configurable": {"thread_id": "sess-ck"}}
    graph.update_state(run_config, initial)
    snapshot = graph.get_state(run_config)
    assert snapshot.values.get("session_id") == "sess-ck"
    result = graph.invoke(None, {**run_config, "recursion_limit": 8})
    assert result.get("session_id") == "sess-ck"
    saved = graph.get_state(run_config)
    assert saved.values.get("current_state") in {"DONE", "EVALUATE", "DISPATCH", "EXECUTE"}


def test_reflection_written_to_decision_log(memory: MemoryStores) -> None:
    slm = MockSLMClient("Use smaller edits.")
    before = len(memory.decisions.list_for_session("sess-wf"))
    text = write_reflection(
        slm,
        "sess-wf",
        1,
        "Build X",
        "fix tests",
        1,
        "pytest failed",
        memory,
        subtask_id="t-1",
    )
    after = len(memory.decisions.list_for_session("sess-wf"))
    assert text
    assert after == before + 1
    last = memory.decisions.get_last_n("sess-wf", 1)[0]
    assert last.kind == "reflection"


def test_reflection_capped_at_max_per_config(memory: MemoryStores) -> None:
    slm = MockSLMClient()
    for _ in range(5):
        write_reflection(
            slm,
            "sess-cap",
            0,
            "goal",
            "sub",
            1,
            "fail",
            memory,
            subtask_id="cap-task",
        )
    reflections = [
        e
        for e in memory.decisions.list_for_session("sess-cap")
        if e.kind == "reflection"
    ]
    assert len(reflections) == 3


def test_graph_uses_sqlite_saver(tmp_path: Path) -> None:
    """Production graph path persists checkpoints via SqliteSaver."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path = tmp_path / "langgraph" / "sess-sqlite.sqlite"
    with sqlite_checkpointer(db_path) as checkpointer:
        assert isinstance(checkpointer, SqliteSaver)
    assert db_path.is_file()


def test_graph_engine_reaches_done_on_passing_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LangGraph engine reaches solved when workspace already passes tests."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "solution.py").write_text(
        "def multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    memory = MemoryStores(SQLiteBackend(tmp_path / "graph_sess.db"))
    memory.subtasks.register(
        SubTask(
            task_id="st-main",
            parent_session_id="sess-graph",
            description="fix multiply",
            status="open",
            owner="executor",
        )
    )

    def _fake_execute(self: ExecutorAgent, state: WorkflowState) -> WorkflowState:
        return {**state, "current_state": "EXECUTE"}

    monkeypatch.setattr(
        "framework.orchestration.session.validate_slm_api_key",
        lambda *args, **kwargs: ProbeResult(ok=True, attempts=1),
    )
    monkeypatch.setattr(ExecutorAgent, "execute_node", _fake_execute)

    result = run_full_session(
        "Fix multiply",
        [],
        "assert multiply(3, 4) == 12",
        workspace,
        memory=memory,
        session_id="sess-graph",
        max_steps=8,
        checkpoint_dir=tmp_path / "checkpoints",
        ablation=AblationSettings(memory=False, control=False, error_control=False),
        planner_enabled=False,
        engine="graph",
    )
    assert result.outcome == "solved"
    assert result.test_passed


def test_graph_and_loop_produce_same_terminal_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph and imperative loop agree on terminal outcome for the same seeded task."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "solution.py").write_text(
        "def multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )

    def _fake_execute(self: ExecutorAgent, state: WorkflowState) -> WorkflowState:
        return {**state, "current_state": "EXECUTE"}

    monkeypatch.setattr(
        "framework.orchestration.session.validate_slm_api_key",
        lambda *args, **kwargs: ProbeResult(ok=True, attempts=1),
    )
    monkeypatch.setattr(ExecutorAgent, "execute_node", _fake_execute)

    kwargs = dict(
        goal="Fix multiply",
        constraints=[],
        test_code="assert multiply(3, 4) == 12",
        workspace=workspace,
        max_steps=8,
        checkpoint_dir=tmp_path / "checkpoints",
        ablation=AblationSettings(memory=False, control=False, error_control=False),
        planner_enabled=False,
    )

    memory_loop = MemoryStores(SQLiteBackend(tmp_path / "loop.db"))
    memory_loop.subtasks.register(
        SubTask(
            task_id="st-main",
            parent_session_id="sess-loop",
            description="fix multiply",
            status="open",
            owner="executor",
        )
    )
    loop_result = run_full_session(
        kwargs["goal"],
        kwargs["constraints"],
        kwargs["test_code"],
        kwargs["workspace"],
        memory=memory_loop,
        session_id="sess-loop",
        engine="loop",
        max_steps=kwargs["max_steps"],
        checkpoint_dir=kwargs["checkpoint_dir"],
        ablation=kwargs["ablation"],
        planner_enabled=kwargs["planner_enabled"],
    )

    memory_graph = MemoryStores(SQLiteBackend(tmp_path / "graph.db"))
    memory_graph.subtasks.register(
        SubTask(
            task_id="st-main",
            parent_session_id="sess-graph-parity",
            description="fix multiply",
            status="open",
            owner="executor",
        )
    )
    graph_result = run_full_session(
        kwargs["goal"],
        kwargs["constraints"],
        kwargs["test_code"],
        kwargs["workspace"],
        memory=memory_graph,
        session_id="sess-graph-parity",
        engine="graph",
        max_steps=kwargs["max_steps"],
        checkpoint_dir=kwargs["checkpoint_dir"],
        ablation=kwargs["ablation"],
        planner_enabled=kwargs["planner_enabled"],
    )

    assert loop_result.outcome == graph_result.outcome == "solved"
    assert loop_result.test_passed and graph_result.test_passed

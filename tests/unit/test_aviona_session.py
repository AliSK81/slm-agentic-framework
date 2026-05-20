"""Aviona session adapter tests — mocked SLM, no API keys."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from aviona.session import AvionaSession, aviona_project_dir, project_hash
from framework.control.workflow import WorkflowState
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord, SubTask
from framework.orchestration.executor import ExecutorAgent
from framework.orchestration.planner import PlannerAgent
from framework.tools.file_tools import write_file


def _self_check() -> SelfCheckRecord:
    return SelfCheckRecord(verdict="pass", issues=[])


def _register_main_subtask(memory: MemoryStores, session_id: str, goal: str) -> None:
    memory.subtasks.register(
        SubTask(
            task_id="st-main",
            parent_session_id=session_id,
            description=goal,
            status="open",
            owner="executor",
        )
    )


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    workspace = tmp_path / "proj"
    workspace.mkdir()
    return workspace


def test_turn_creates_file_in_cwd(
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_turn drives the graph; mocked execute writes hello.txt under cwd."""
    session = AvionaSession(project_dir)

    def _noop_plan(self: PlannerAgent, state: WorkflowState) -> WorkflowState:
        return state

    def _fake_dispatch(self: PlannerAgent, state: WorkflowState) -> WorkflowState:
        return {**state, "active_subtask_id": "st-main", "current_state": "DISPATCH"}

    def _fake_execute(self: ExecutorAgent, state: WorkflowState) -> WorkflowState:
        write_file("hello.txt", "hi\n", project_dir)
        return {**state, "current_state": "EXECUTE"}

    monkeypatch.setattr(PlannerAgent, "plan_node", _noop_plan)
    monkeypatch.setattr(PlannerAgent, "dispatch_node", _fake_dispatch)
    monkeypatch.setattr(ExecutorAgent, "execute_node", _fake_execute)

    _register_main_subtask(session.memory, session._session_id, "create hello.txt")

    result = session.run_turn("create hello.txt with hi")
    assert (project_dir / "hello.txt").is_file()
    assert (project_dir / "hello.txt").read_text(encoding="utf-8") == "hi\n"
    assert result.test_passed or result.outcome == "solved"


def test_write_outside_cwd_refused(project_dir: Path) -> None:
    """file_tools write-guard rejects paths outside the session workspace."""
    result = write_file("../escape.txt", "secret\n", project_dir)
    assert not result.ok
    assert "outside" in result.message.lower()


def test_memory_db_persists_between_turns(
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two turns share the same SQLite memory store under ~/.aviona/projects/."""
    session = AvionaSession(project_dir)
    db_path = session.session_root / "memory.db"
    assert db_path.is_file()

    turn_calls: list[str] = []

    def _noop_plan(self: PlannerAgent, state: WorkflowState) -> WorkflowState:
        return state

    def _fake_dispatch(self: PlannerAgent, state: WorkflowState) -> WorkflowState:
        return {**state, "active_subtask_id": "st-main", "current_state": "DISPATCH"}

    def _fake_execute(self: ExecutorAgent, state: WorkflowState) -> WorkflowState:
        return {**state, "current_state": "EXECUTE"}

    monkeypatch.setattr(PlannerAgent, "plan_node", _noop_plan)
    monkeypatch.setattr(PlannerAgent, "dispatch_node", _fake_dispatch)
    monkeypatch.setattr(ExecutorAgent, "execute_node", _fake_execute)
    _register_main_subtask(session.memory, session._session_id, "noop")

    session.memory.decisions.append(
        DecisionEntry(
            session_id=session._session_id,
            decision_id="d-before",
            step_index=0,
            by_agent="executor",
            kind="tool_call",
            payload={"tool": "noop"},
            rationale="seed",
            references=[],
            self_check=_self_check(),
            timestamp=datetime.now(UTC),
        )
    )
    before = len(session.memory.decisions.list_for_session(session._session_id))

    session.run_turn("first")
    turn_calls.append("first")
    session.run_turn("second")
    turn_calls.append("second")

    after = len(session.memory.decisions.list_for_session(session._session_id))
    assert after >= before
    assert len(turn_calls) == 2
    assert project_hash(project_dir) == project_hash(project_dir.resolve())
    assert aviona_project_dir(project_dir) == session.session_root

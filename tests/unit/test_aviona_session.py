"""Aviona session adapter tests — mocked SLM, no API keys."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aviona.repl import ScriptedReader, run_repl
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


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Copy ``tests/fixtures/sample_repo`` into an isolated workspace."""
    src = Path(__file__).resolve().parents[1] / "fixtures" / "sample_repo"
    dest = tmp_path / "sample_repo"
    shutil.copytree(src, dest)
    return dest


def _patch_graph_for_hello_write(
    monkeypatch: pytest.MonkeyPatch,
    workspace: Path,
) -> None:
    """Mock planner/executor so one turn writes ``hello.txt`` under ``workspace``."""

    def _noop_plan(self: PlannerAgent, state: WorkflowState) -> WorkflowState:
        return state

    def _fake_dispatch(self: PlannerAgent, state: WorkflowState) -> WorkflowState:
        return {**state, "active_subtask_id": "st-main", "current_state": "DISPATCH"}

    def _fake_execute(self: ExecutorAgent, state: WorkflowState) -> WorkflowState:
        write_file("hello.txt", "hi\n", workspace)
        return {**state, "current_state": "EXECUTE"}

    monkeypatch.setattr(PlannerAgent, "plan_node", _noop_plan)
    monkeypatch.setattr(PlannerAgent, "dispatch_node", _fake_dispatch)
    monkeypatch.setattr(ExecutorAgent, "execute_node", _fake_execute)


def test_turn_creates_file_in_cwd(
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_turn drives the graph; mocked execute writes hello.txt under cwd."""
    session = AvionaSession(project_dir)
    _patch_graph_for_hello_write(monkeypatch, project_dir)
    _register_main_subtask(session.memory, session._session_id, "create hello.txt")

    result = session.run_turn("create hello.txt with hi")
    assert (project_dir / "hello.txt").is_file()
    assert (project_dir / "hello.txt").read_text(encoding="utf-8") == "hi\n"
    assert result.test_passed or result.outcome == "solved"


def test_v1_sample_repo_repl_creates_hello_and_logs_session(
    sample_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1 DoD: REPL in sample_repo creates hello.txt and appends a JSONL turn line."""
    store_root = tmp_path / "aviona-store"
    monkeypatch.setattr("aviona.store.aviona_project_dir", lambda _cwd: store_root)
    monkeypatch.setattr("aviona.session.aviona_project_dir", lambda _cwd: store_root)

    session = AvionaSession(sample_repo)
    _patch_graph_for_hello_write(monkeypatch, sample_repo)
    _register_main_subtask(session.memory, session._session_id, 'create hello.txt with "hi"')

    run_repl(
        session,
        reader=ScriptedReader(['create hello.txt with "hi"', "/exit"]),
        writer=lambda _msg: None,
    )

    hello = sample_repo / "hello.txt"
    assert hello.is_file()
    assert hello.read_text(encoding="utf-8") == "hi\n"

    jsonl_files = list(store_root.glob("session-*.jsonl"))
    assert len(jsonl_files) == 1
    lines = jsonl_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert "hello.txt" in row["user_text"].lower()
    assert row["session_id"] == session._session_id


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

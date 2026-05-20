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
from framework.tools.file_tools import write_file


def _self_check() -> SelfCheckRecord:
    return SelfCheckRecord(verdict="pass", issues=[])


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


def _patch_interactive_write(
    monkeypatch: pytest.MonkeyPatch,
    workspace: Path,
    *,
    user_message: str = "Created hello.txt.",
) -> None:
    """Mock executor interactive turn: write file + typed terminate."""

    def _fake_execute(self: ExecutorAgent, state: WorkflowState) -> WorkflowState:
        write_file("hello.txt", "hi\n", workspace)
        self._memory.decisions.append(
            DecisionEntry(
                session_id=state["session_id"],
                decision_id=f"d-exec-{len(self._memory.decisions.list_for_session(state['session_id']))}",
                step_index=0,
                by_agent="executor",
                kind="terminate",
                payload={
                    "user_message": user_message,
                    "turn_type": "edit",
                },
                rationale=user_message,
                references=[],
                self_check=_self_check(),
                timestamp=datetime.now(UTC),
            )
        )
        return {
            **state,
            "current_state": "EXECUTE",
            "last_evaluation": {"passed": True},
        }

    monkeypatch.setattr(ExecutorAgent, "execute_node", _fake_execute)


def test_turn_creates_file_in_cwd(
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_turn drives interactive mode; mocked execute writes hello.txt under cwd."""
    session = AvionaSession(project_dir)
    _patch_interactive_write(monkeypatch, project_dir)

    result = session.run_turn("create hello.txt with hi")
    assert (project_dir / "hello.txt").is_file()
    assert (project_dir / "hello.txt").read_text(encoding="utf-8") == "hi\n"
    assert result.test_passed or result.outcome == "solved"
    assert result.detail == "Created hello.txt."


def test_v1_sample_repo_repl_creates_hello_and_logs_session(
    sample_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REPL in sample_repo creates hello.txt and appends a JSONL turn line."""
    store_root = tmp_path / "aviona-store"
    monkeypatch.setattr("aviona.store.aviona_project_dir", lambda _cwd: store_root)
    monkeypatch.setattr("aviona.session.aviona_project_dir", lambda _cwd: store_root)

    session = AvionaSession(sample_repo)
    _patch_interactive_write(monkeypatch, sample_repo)

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

    def _noop_execute(self: ExecutorAgent, state: WorkflowState) -> WorkflowState:
        turn_calls.append(state["session_id"])
        self._memory.decisions.append(
            DecisionEntry(
                session_id=state["session_id"],
                decision_id=f"d-{len(turn_calls)}",
                step_index=0,
                by_agent="executor",
                kind="terminate",
                payload={"user_message": "ok", "turn_type": "answer"},
                rationale="ok",
                references=[],
                self_check=_self_check(),
                timestamp=datetime.now(UTC),
            )
        )
        return {
            **state,
            "current_state": "EXECUTE",
            "last_evaluation": {"passed": True},
        }

    monkeypatch.setattr(ExecutorAgent, "execute_node", _noop_execute)

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
    session.run_turn("second")

    after = len(session.memory.decisions.list_for_session(session._session_id))
    assert after > before
    assert len(turn_calls) == 2
    assert project_hash(project_dir) == project_hash(project_dir.resolve())
    assert aviona_project_dir(project_dir) == session.session_root

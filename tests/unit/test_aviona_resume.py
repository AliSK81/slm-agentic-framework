"""Aviona session resume and fork unit tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aviona.cli import main
from aviona.session import AvionaSession
from aviona.store import (
    SessionNotFoundError,
    SessionStore,
    fork_session,
    latest_session,
    list_sessions,
    load_session,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    return proj


def test_write_session_then_continue_reloads_same_id(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--continue reopens the latest session and appends to its JSONL."""
    monkeypatch.setattr(
        "aviona.store.aviona_project_dir",
        lambda _cwd: workspace / ".aviona-store",
    )
    first = AvionaSession(workspace)
    first._store.append_turn(
        user_text="hello",
        status="ok",
        outcome="solved",
        tokens_total=1,
        decision_refs=[],
    )
    sid = first._session_id

    latest = latest_session(workspace)
    assert latest is not None
    assert latest.session_id == sid

    second = AvionaSession(workspace, session_id=sid)
    second._store.append_turn(
        user_text="world",
        status="ok",
        outcome="solved",
        tokens_total=2,
        decision_refs=[],
    )
    lines = second._store.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_resume_specific_session_id(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """load_session reattaches a known session id."""
    store_root = workspace / ".aviona-store"
    monkeypatch.setattr("aviona.store.aviona_project_dir", lambda _cwd: store_root)

    store = SessionStore(workspace, "aviona-abc11111")
    store.append_turn(
        user_text="one",
        status="ok",
        outcome="solved",
        tokens_total=0,
        decision_refs=[],
    )
    record = load_session(workspace, "aviona-abc11111")
    assert record.session_id == "aviona-abc11111"
    assert Path(record.jsonl_path).is_file()

    session = AvionaSession(workspace, session_id="aviona-abc11111")
    assert session._session_id == "aviona-abc11111"
    assert session.memory is not None


def test_fork_creates_linked_new_session(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fork creates a new session id with parent_session_id in meta."""
    store_root = workspace / ".aviona-store"
    monkeypatch.setattr("aviona.store.aviona_project_dir", lambda _cwd: store_root)

    parent = SessionStore(workspace, "aviona-parent1")
    parent.append_turn(
        user_text="seed",
        status="ok",
        outcome="solved",
        tokens_total=0,
        decision_refs=[],
    )

    child = fork_session(workspace, "aviona-parent1")
    assert child.session_id != "aviona-parent1"
    meta = json.loads(Path(child.meta_path).read_text(encoding="utf-8"))
    assert meta["parent_session_id"] == "aviona-parent1"
    assert Path(child.jsonl_path).is_file()

    sessions = list_sessions(workspace)
    assert len(sessions) >= 2


def test_unknown_session_id_raises(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown session id raises SessionNotFoundError."""
    monkeypatch.setattr(
        "aviona.store.aviona_project_dir",
        lambda _cwd: workspace / ".aviona-store",
    )
    with pytest.raises(SessionNotFoundError, match="unknown session"):
        load_session(workspace, "aviona-missing")


def test_cli_continue_unknown_exits_nonzero(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI --continue with no sessions exits 1."""
    monkeypatch.chdir(workspace)
    monkeypatch.setattr("aviona.cli.load_aviona_env", lambda _cwd=None: None)
    monkeypatch.setattr("aviona.cli.validate_slm_api_key", lambda *a, **k: None)
    monkeypatch.setattr(
        "aviona.cli.latest_session",
        lambda _cwd: None,
    )
    assert main(["--continue"]) == 1


def test_cli_resume_unknown_exits_nonzero(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI --resume unknown id prints error and exits 1."""
    monkeypatch.chdir(workspace)
    monkeypatch.setattr("aviona.cli.load_aviona_env", lambda _cwd=None: None)
    monkeypatch.setattr("aviona.cli.validate_slm_api_key", lambda *a, **k: None)
    monkeypatch.setattr(
        "aviona.cli.AvionaSession",
        lambda *_a, **_k: (_ for _ in ()).throw(SessionNotFoundError("unknown session: bad")),
    )
    assert main(["--resume", "bad"]) == 1


def test_cli_fork_session_uses_latest(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--fork-session without --resume forks from the latest session."""
    monkeypatch.chdir(workspace)
    monkeypatch.setattr("aviona.cli.load_aviona_env", lambda _cwd=None: None)
    monkeypatch.setattr("aviona.cli.validate_slm_api_key", lambda *a, **k: None)
    monkeypatch.setattr(
        "aviona.cli.latest_session",
        lambda _cwd: MagicMock(session_id="aviona-parent1"),
    )
    created: list[str] = []

    def _fork_session(cwd, fork_from=None, session_id=None, **_k):
        _ = cwd, session_id
        created.append(fork_from)
        session = MagicMock()
        session._session_id = "aviona-child1"
        return session

    monkeypatch.setattr("aviona.cli.AvionaSession", _fork_session)
    monkeypatch.setattr("aviona.cli.run_repl", lambda _s: 0)
    assert main(["--fork-session"]) == 0
    assert created == ["aviona-parent1"]

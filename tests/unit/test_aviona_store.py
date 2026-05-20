"""Aviona session store unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aviona.store import SessionStore, assert_no_secrets, project_hash


def test_project_hash_stable_for_same_cwd(tmp_path: Path) -> None:
    """Project hash is stable for the same resolved path."""
    workspace = tmp_path / "proj"
    workspace.mkdir()
    assert project_hash(workspace) == project_hash(workspace.resolve())


def test_append_turn_writes_jsonl_and_meta(tmp_path: Path) -> None:
    """Each turn appends one JSONL line and updates meta.json."""
    workspace = tmp_path / "proj"
    workspace.mkdir()
    store = SessionStore(workspace, "sess-test01")
    store.append_turn(
        user_text="create hello.txt",
        status="ok · 1 steps",
        outcome="solved",
        tokens_total=42,
        decision_refs=["d-1", "d-2"],
    )
    assert store.jsonl_path.is_file()
    lines = store.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["user_text"] == "create hello.txt"
    assert row["tokens_total"] == 42
    assert row["decision_refs"] == ["d-1", "d-2"]

    meta = json.loads(store.meta_path.read_text(encoding="utf-8"))
    assert meta["turn_count"] == 1
    assert meta["session_id"] == "sess-test01"
    assert meta["project_hash"] == project_hash(workspace)


def test_append_turn_second_line_increments_meta(tmp_path: Path) -> None:
    """Multiple turns append multiple JSONL lines."""
    workspace = tmp_path / "proj"
    workspace.mkdir()
    store = SessionStore(workspace, "sess-test02")
    store.append_turn(
        user_text="first",
        status="ok",
        outcome="solved",
        tokens_total=1,
        decision_refs=[],
    )
    store.append_turn(
        user_text="second",
        status="ok",
        outcome="solved",
        tokens_total=2,
        decision_refs=["d-3"],
    )
    assert len(store.jsonl_path.read_text(encoding="utf-8").strip().splitlines()) == 2
    meta = json.loads(store.meta_path.read_text(encoding="utf-8"))
    assert meta["turn_count"] == 2


def test_assert_no_secrets_rejects_api_key_shaped_text() -> None:
    """Secret-shaped strings are refused before persistence."""
    with pytest.raises(ValueError, match="secret"):
        assert_no_secrets('{"api_key": "sk-abcdefghijklmnopqrstuvwxyz123456"}')


def test_append_turn_refuses_secret_in_user_text(tmp_path: Path) -> None:
    """append_turn raises when user text contains secret patterns."""
    workspace = tmp_path / "proj"
    workspace.mkdir()
    store = SessionStore(workspace, "sess-secret")
    with pytest.raises(ValueError, match="secret"):
        store.append_turn(
            user_text="key is sk-abcdefghijklmnopqrstuvwxyz1234567890",
            status="ok",
            outcome="solved",
            tokens_total=0,
            decision_refs=[],
        )
    assert not store.jsonl_path.exists() or store.jsonl_path.read_text() == ""

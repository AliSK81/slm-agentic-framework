"""Aviona snapshot and undo unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aviona.snapshots import SnapshotStore
from aviona.tools import snapshotting_edit, snapshotting_write
from framework.tools.file_tools import edit_file, write_file


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    return proj


def test_edit_then_undo_restores_original_bytes(workspace: Path) -> None:
    """Undo restores pre-edit file content."""
    target = workspace / "module.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")
    store = SnapshotStore(workspace)
    store.begin_turn()
    snapshotting_edit(store, "module.py", "return 1", "return 2", workspace)
    store.end_turn()
    assert "return 2" in target.read_text(encoding="utf-8")

    restored = store.undo_last()
    assert restored == ["module.py"]
    assert target.read_text(encoding="utf-8") == "def foo():\n    return 1\n"


def test_undo_with_no_snapshot_is_friendly_noop(workspace: Path) -> None:
    """undo_last returns empty when the stack is empty."""
    store = SnapshotStore(workspace)
    assert store.undo_last() == []


def test_undo_removes_file_created_in_turn(workspace: Path) -> None:
    """Undo deletes a file that did not exist before the turn."""
    store = SnapshotStore(workspace)
    store.begin_turn()
    snapshotting_write(store, "hello.txt", "hi\n", workspace)
    store.end_turn()
    assert (workspace / "hello.txt").is_file()

    restored = store.undo_last()
    assert "hello.txt" in restored
    assert not (workspace / "hello.txt").exists()


def test_snapshot_refuses_paths_outside_workspace(workspace: Path) -> None:
    """Snapshots are scoped to the project workspace."""
    store = SnapshotStore(workspace)
    store.begin_turn()
    result = snapshotting_write(store, "../escape.txt", "x\n", workspace)
    store.end_turn()
    assert not result.ok
    assert "outside" in result.message.lower()


def test_write_guard_still_enforced_through_wrapper(workspace: Path) -> None:
    """snapshotting_write preserves framework write-guard."""
    (workspace / "exists.py").write_text("original\n", encoding="utf-8")
    store = SnapshotStore(workspace)
    store.begin_turn()
    result = snapshotting_write(store, "exists.py", "new\n", workspace)
    store.end_turn()
    assert not result.ok
    assert "Write guard" in result.message or "edit_file" in result.message
    assert (workspace / "exists.py").read_text(encoding="utf-8") == "original\n"


def test_ast_gate_still_enforced_through_wrapper(workspace: Path) -> None:
    """snapshotting_edit preserves AST gate on Python files."""
    (workspace / "bad.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    store = SnapshotStore(workspace)
    store.begin_turn()
    result = snapshotting_edit(store, "bad.py", "return 1", "return (", workspace)
    store.end_turn()
    assert not result.ok
    assert "AST gate" in result.message
    assert (workspace / "bad.py").read_text(encoding="utf-8") == "def ok():\n    return 1\n"


def test_direct_write_still_works_without_snapshot(workspace: Path) -> None:
    """Baseline: framework write_file unchanged."""
    result = write_file("new.py", "x = 1\n", workspace)
    assert result.ok

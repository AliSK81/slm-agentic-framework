"""Aviona file-tool wrappers (snapshot before mutate, delegate to framework)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from aviona.snapshots import SnapshotStore
from framework.tools.file_tools import FileResult, edit_file, write_file

WriteFn = Callable[[str, str, Path], FileResult]
EditFn = Callable[[str, str, str, Path], FileResult]


class SnapshotStoreLike(Protocol):
    """Minimal snapshot store surface for wrappers."""

    def before_mutation(self, file_path: str) -> None: ...


def snapshotting_write(
    store: SnapshotStoreLike,
    file_path: str,
    content: str,
    workspace: Path,
) -> FileResult:
    """Snapshot then delegate to ``write_file`` (write-guard + AST gate preserved)."""
    store.before_mutation(file_path)
    return write_file(file_path, content, workspace)


def snapshotting_edit(
    store: SnapshotStoreLike,
    file_path: str,
    old_string: str,
    new_string: str,
    workspace: Path,
) -> FileResult:
    """Snapshot then delegate to ``edit_file``."""
    store.before_mutation(file_path)
    return edit_file(file_path, old_string, new_string, workspace)


def bind_snapshot_tools(
    store: SnapshotStore,
    workspace: Path,
) -> tuple[WriteFn, EditFn]:
    """Return ``(write_fn, edit_fn)`` bound for ``ExecutorAgent`` injection."""

    def _write(file_path: str, content: str, ws: Path) -> FileResult:
        _ = ws
        return snapshotting_write(store, file_path, content, workspace)

    def _edit(
        file_path: str,
        old_string: str,
        new_string: str,
        ws: Path,
    ) -> FileResult:
        _ = ws
        return snapshotting_edit(store, file_path, old_string, new_string, workspace)

    return _write, _edit

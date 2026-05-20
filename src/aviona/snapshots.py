"""Pre-edit file snapshots for Aviona undo."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from aviona.store import aviona_project_dir

logger = logging.getLogger(__name__)

_MANIFEST = "manifest.json"


class SnapshotEntry(BaseModel):
    """One file captured before mutation."""

    rel_path: str
    existed: bool
    snapshot_relpath: str | None = None


class TurnManifest(BaseModel):
    """Manifest for a single turn's snapshots."""

    turn_id: str
    entries: list[SnapshotEntry] = Field(default_factory=list)


class SnapshotStore:
    """Store pre-mutation bytes under ``~/.aviona/projects/<hash>/snapshots/<turn>/``."""

    def __init__(self, workspace: Path, *, store_root: Path | None = None) -> None:
        self.workspace = workspace.resolve()
        root = store_root or aviona_project_dir(self.workspace)
        self.snapshots_root = root / "snapshots"
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        self._turn_stack: list[str] = []
        self._current_turn: str | None = None
        self._snapshotted: set[str] = set()

    def begin_turn(self) -> str:
        """Start a new turn snapshot bucket."""
        turn_id = f"turn-{len(self._turn_stack) + 1:04d}-{uuid.uuid4().hex[:6]}"
        self._current_turn = turn_id
        self._snapshotted = set()
        (self.snapshots_root / turn_id).mkdir(parents=True, exist_ok=True)
        return turn_id

    def end_turn(self) -> None:
        """Finalize the current turn and push it onto the undo stack."""
        if self._current_turn is None:
            return
        self._turn_stack.append(self._current_turn)
        self._current_turn = None
        self._snapshotted = set()

    def before_mutation(self, file_path: str) -> None:
        """Copy prior bytes (or record absence) before a write/edit.

        Args:
            file_path: Path relative to the project workspace.

        Side effects:
            Writes snapshot bytes under the active turn directory.
        """
        if self._current_turn is None:
            return
        rel = file_path.replace("\\", "/").lstrip("/")
        if rel in self._snapshotted:
            return
        target = (self.workspace / rel).resolve()
        try:
            target.relative_to(self.workspace)
        except ValueError:
            logger.warning("Snapshot skipped for path outside workspace: %s", file_path)
            return

        turn_dir = self.snapshots_root / self._current_turn
        manifest = self._load_manifest(turn_dir)
        entry = SnapshotEntry(rel_path=rel, existed=target.is_file())
        if target.is_file():
            snap_name = f"files/{rel}"
            snap_path = turn_dir / snap_name
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, snap_path)
            entry.snapshot_relpath = snap_name.replace("\\", "/")
        manifest.entries.append(entry)
        self._write_manifest(turn_dir, manifest)
        self._snapshotted.add(rel)

    def undo_last(self) -> list[str]:
        """Restore files from the most recent turn snapshot.

        Returns:
            Workspace-relative paths restored. Empty when there is nothing to undo.
        """
        if not self._turn_stack:
            return []
        turn_id = self._turn_stack.pop()
        turn_dir = self.snapshots_root / turn_id
        if not turn_dir.is_dir():
            return []
        manifest = self._load_manifest(turn_dir)
        restored: list[str] = []
        for entry in reversed(manifest.entries):
            dest = self.workspace / entry.rel_path
            if entry.existed and entry.snapshot_relpath:
                src = turn_dir / entry.snapshot_relpath
                if not src.is_file():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                restored.append(entry.rel_path)
            elif not entry.existed and dest.is_file():
                dest.unlink()
                restored.append(entry.rel_path)
        return restored

    def _load_manifest(self, turn_dir: Path) -> TurnManifest:
        path = turn_dir / _MANIFEST
        if not path.is_file():
            return TurnManifest(turn_id=turn_dir.name)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return TurnManifest.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Invalid snapshot manifest %s: %s", path, exc)
            return TurnManifest(turn_id=turn_dir.name)

    @staticmethod
    def _write_manifest(turn_dir: Path, manifest: TurnManifest) -> None:
        path = turn_dir / _MANIFEST
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

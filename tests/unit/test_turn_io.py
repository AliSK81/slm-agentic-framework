"""Unit tests for factual turn I/O helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import time

from aviona.turn_io import (
    changed_files,
    changed_paths_for_turn,
    collect_tool_paths,
    declared_turn_type,
    snapshot_files,
)
from framework.memory.stores import DecisionEntry, SelfCheckRecord


def _entry(kind: str, payload: dict) -> DecisionEntry:
    return DecisionEntry(
        session_id="s1",
        decision_id="d1",
        step_index=0,
        by_agent="executor",
        kind=kind,  # type: ignore[arg-type]
        payload=payload,
        rationale="because test",
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


def test_snapshot_and_changed_files(tmp_path: Path) -> None:
    """changed_files detects new and modified workspace paths."""
    before = snapshot_files(tmp_path)
    target = tmp_path / "a.txt"
    target.write_text("one", encoding="utf-8")
    after = snapshot_files(tmp_path)
    assert changed_files(before, after) == ["a.txt"]
    time.sleep(0.02)
    target.write_text("two", encoding="utf-8")
    after2 = snapshot_files(tmp_path)
    assert changed_files(after, after2) == ["a.txt"]


def test_collect_tool_paths_from_decisions() -> None:
    """Decision log paths merge with filesystem snapshots."""
    entries = [
        _entry("tool_call", {"tool": "write_file", "file_path": "foo.txt"}),
        _entry("tool_call", {"tool": "read_file", "file_path": "bar.txt"}),
    ]
    edited, listed, read_paths = collect_tool_paths(entries)
    assert edited == ["foo.txt"]
    assert read_paths == ["bar.txt"]
    assert listed == []


def test_declared_turn_type_reads_agent_payload() -> None:
    """turn_type comes from terminate payload when present."""
    entries = [
        _entry(
            "terminate",
            {"user_message": "hello", "turn_type": "inspect"},
        )
    ]
    assert declared_turn_type(entries, file_changes=[]) == "inspect"


def test_declared_turn_type_infers_edit_on_writes() -> None:
    """Missing turn_type with file changes defaults to edit."""
    entries = [_entry("tool_call", {"tool": "write_file", "file_path": "x.txt"})]
    assert declared_turn_type(entries, file_changes=["x.txt"]) == "edit"

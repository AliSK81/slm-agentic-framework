"""Executor agent unit tests (write guard)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord
from framework.orchestration.executor import ExecutorAgent
from framework.tools.file_tools import FileResult


def _memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores.sqlite(tmp_path / "exec.db")


def _entry(payload: dict) -> DecisionEntry:
    return DecisionEntry(
        session_id="sess-ex",
        decision_id="d-1",
        step_index=0,
        by_agent="executor",
        kind="code_edit",
        payload=payload,
        rationale="edit code",
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def test_apply_code_edit_full_file_replace_without_old_string(
    workspace: Path,
    tmp_path: Path,
) -> None:
    """Full replacement via code/new_string when old_string is omitted."""
    (workspace / "solution.py").write_text("def add(a, b):\n    pass\n", encoding="utf-8")
    agent = ExecutorAgent(object(), _memory(tmp_path), workspace)  # type: ignore[arg-type]
    result = agent._apply_code_edit(
        _entry(
            {
                "file_path": "solution.py",
                "code": "def add(a, b):\n    return a + b\n",
            }
        )
    )
    assert result.ok
    assert "return a + b" in (workspace / "solution.py").read_text(encoding="utf-8")


def test_apply_code_edit_resolves_file_path_camel_case(
    workspace: Path,
    tmp_path: Path,
) -> None:
    """filePath alias is accepted in code_edit payloads."""
    agent = ExecutorAgent(object(), _memory(tmp_path), workspace)  # type: ignore[arg-type]
    result = agent._apply_code_edit(
        _entry(
            {
                "filePath": "helper.py",
                "content": "def helper():\n    return 1\n",
            }
        )
    )
    assert result.ok
    assert (workspace / "helper.py").is_file()

"""FI-6: inspect-run commands auto-allowed on declared inspect turns."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework.error_control.sandbox import is_inspect_run_command
from framework.memory.stores import DecisionEntry, SelfCheckRecord
from framework.orchestration.executor import ExecutorAgent
from framework.tools.file_tools import FileResult


def _decision(*, kind: str, payload: dict[str, object]) -> DecisionEntry:
    return DecisionEntry(
        session_id="sess",
        decision_id="d-test",
        step_index=0,
        by_agent="executor",
        kind=kind,
        rationale="test",
        payload=payload,
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    "cmd",
    [
        "pytest tests/",
        "pytest -q",
        "python -m pytest tests/unit",
        "python -c \"import sys; print(sys.version)\"",
    ],
)
def test_is_inspect_run_command_accepts_run_safe_commands(cmd: str) -> None:
    """Run-safe pytest and python -c commands classify as inspect-run."""
    assert is_inspect_run_command(cmd)


def test_is_inspect_run_command_rejects_empty() -> None:
    """Empty commands are not inspect-run."""
    assert not is_inspect_run_command("")


def test_inspect_turn_auto_allows_pytest_without_permission_gate() -> None:
    """Declared inspect + pytest bypasses permission_check (no ask)."""
    calls: list[tuple[str, str]] = []

    def deny_all(kind: str, detail: str) -> bool:
        calls.append((kind, detail))
        return False

    executor = ExecutorAgent(
        object(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        Path("."),
        permission_check=deny_all,
        interactive_read_only=True,
    )
    decision = _decision(
        kind="tool_call",
        payload={"tool": "pytest", "target": ".", "turn_type": "inspect"},
    )
    blocked = executor._require_permission(
        "run_tests", "pytest .", decision=decision
    )
    assert blocked is None
    assert calls == []


def test_inspect_turn_still_blocks_writes_on_read_only() -> None:
    """Inspect turn_type does not permit file writes on read-only interactive turns."""
    executor = ExecutorAgent(
        object(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        Path("."),
        permission_check=lambda _k, _d: True,
        interactive_read_only=True,
    )
    decision = _decision(
        kind="tool_call",
        payload={"tool": "write_file", "file_path": "x.py", "turn_type": "inspect"},
    )
    blocked = executor._require_permission(
        "write_file", "x.py", decision=decision
    )
    assert blocked is not None
    assert isinstance(blocked, FileResult)
    assert not blocked.ok


def test_non_inspect_turn_still_uses_permission_gate() -> None:
    """Without turn_type inspect, permission_check still applies."""
    calls: list[tuple[str, str]] = []

    def deny_all(kind: str, detail: str) -> bool:
        calls.append((kind, detail))
        return False

    executor = ExecutorAgent(
        object(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        Path("."),
        permission_check=deny_all,
        interactive_read_only=True,
    )
    decision = _decision(
        kind="tool_call",
        payload={"tool": "shell", "command": "pytest .", "turn_type": "edit"},
    )
    blocked = executor._require_permission("shell", "pytest .", decision=decision)
    assert blocked is not None
    assert calls == [("shell", "pytest .")]

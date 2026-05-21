"""FI-3: after a successful tool, next proposal must terminate or a new tool."""

from __future__ import annotations

from datetime import UTC, datetime

from framework.control.interactive import (
    InteractiveCompletionState,
    icp_after_successful_tool,
    icp_issues,
)
from framework.memory.stores import DecisionEntry, SelfCheckRecord


def _proposal(kind: str, payload: dict | None = None) -> DecisionEntry:
    return DecisionEntry(
        session_id="s1",
        decision_id="d-1",
        step_index=0,
        by_agent="executor",
        kind=kind,  # type: ignore[arg-type]
        payload=payload or {},
        rationale="because",
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


def test_must_terminate_after_tool_rejects_second_tool_call() -> None:
    """After list_dir ok, another list_dir is repeat_tool; read_file is allowed once."""
    icp = icp_after_successful_tool(
        InteractiveCompletionState(),
        "list_dir:.",
    )
    repeat = icp_issues(
        _proposal("tool_call", {"tool": "list_dir", "path": "."}),
        icp,
    )
    assert any(i.kind == "repeat_tool" for i in repeat)

    new_tool = icp_issues(
        _proposal("tool_call", {"tool": "read_file", "file_path": "a.txt"}),
        icp,
    )
    assert new_tool == []


def test_must_terminate_after_tool_requires_terminate_or_new_tool() -> None:
    """After tool ok, code_edit is rejected with must_terminate_after_tool."""
    icp = icp_after_successful_tool(
        InteractiveCompletionState(),
        "read_file:solution.py",
    )
    issues = icp_issues(
        _proposal("code_edit", {"file_path": "x.txt", "turn_type": "edit"}),
        icp,
    )
    assert any(i.kind == "must_terminate_after_tool" for i in issues)

    ok = icp_issues(
        _proposal("terminate", {"user_message": "done", "turn_type": "inspect"}),
        icp,
    )
    assert ok == []


def test_must_terminate_after_edit() -> None:
    """After code_edit, only terminate is allowed."""
    icp = InteractiveCompletionState(
        phase="must_finalize_or_continue",
        after_edit=True,
    )
    issues = icp_issues(
        _proposal("tool_call", {"tool": "read_file", "file_path": "a.txt"}),
        icp,
    )
    assert any(i.kind == "must_terminate_after_edit" for i in issues)

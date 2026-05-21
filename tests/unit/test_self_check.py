"""SELF_CHECK unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework.control.self_check import self_check
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord


def _entry(
    *,
    decision_id: str = "d-1",
    by_agent: str = "executor",
    kind: str = "tool_call",
    payload: dict | None = None,
    rationale: str = "run tool",
) -> DecisionEntry:
    return DecisionEntry(
        session_id="sess-sc",
        decision_id=decision_id,
        step_index=0,
        by_agent=by_agent,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        payload=payload or {"tool": "pytest"},
        rationale=rationale,
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "self_check.db"))


def test_self_check_passes_valid_proposal(memory: MemoryStores) -> None:
    proposal = _entry()
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "pass"
    assert result.issues == []


def test_self_check_fails_missing_rationale(memory: MemoryStores) -> None:
    proposal = _entry(rationale="   ")
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "fail"
    assert any(i.kind == "empty" for i in result.issues)


def test_self_check_fails_scope_violation_executor_plan(memory: MemoryStores) -> None:
    proposal = _entry(by_agent="executor", kind="plan_step")
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "fail"
    assert any(i.kind == "scope_violation" for i in result.issues)


def test_self_check_allows_executor_terminate(memory: MemoryStores) -> None:
    """Interactive REPL executor must pass terminate through SELF_CHECK."""
    proposal = _entry(
        by_agent="executor",
        kind="terminate",
        payload={"user_message": "Hello.", "turn_type": "answer"},
        rationale="Answer the greeting.",
    )
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "pass"


def test_self_check_allows_different_terminate_user_message_per_turn(
    memory: MemoryStores,
) -> None:
    """Each REPL turn may terminate with a different user_message."""
    prior = _entry(
        decision_id="d-old",
        kind="terminate",
        payload={"user_message": "ali ali", "turn_type": "answer"},
        rationale="greeting",
    )
    memory.decisions.append(prior)
    proposal = _entry(
        decision_id="d-new",
        kind="terminate",
        payload={
            "user_message": "My LLM model is deepseek-v4-flash.",
            "turn_type": "answer",
        },
        rationale="runtime facts",
    )
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "pass"


def test_self_check_fails_scope_violation_planner_tool(memory: MemoryStores) -> None:
    proposal = _entry(by_agent="planner", kind="tool_call")
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "fail"
    assert any(i.kind == "scope_violation" for i in result.issues)


def test_self_check_detects_contradiction_same_key_different_value(
    memory: MemoryStores,
) -> None:
    prior = _entry(
        decision_id="d-old",
        by_agent="planner",
        kind="plan_step",
        payload={"phase": "design"},
        rationale="plan a",
    )
    memory.decisions.append(prior)
    proposal = _entry(
        decision_id="d-new",
        by_agent="planner",
        kind="plan_step",
        payload={"phase": "implement"},
        rationale="plan b",
    )
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "fail"
    assert any(i.kind == "contradiction" for i in result.issues)


def test_self_check_no_contradiction_when_log_empty(memory: MemoryStores) -> None:
    proposal = _entry(payload={"tool": "pytest"})
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "pass"


def test_self_check_no_contradiction_same_key_same_value(memory: MemoryStores) -> None:
    prior = _entry(decision_id="d-old", payload={"tool": "pytest"})
    memory.decisions.append(prior)
    proposal = _entry(decision_id="d-new", payload={"tool": "pytest"})
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "pass"


def test_self_check_allows_varying_tool_on_tool_call_retry(
    memory: MemoryStores,
) -> None:
    """Tool retries may switch tools without contradiction."""
    prior = _entry(
        decision_id="d-old",
        kind="tool_call",
        payload={"tool": "exec", "args": {"command": "type hello.txt"}},
    )
    memory.decisions.append(prior)
    proposal = _entry(
        decision_id="d-new",
        kind="tool_call",
        payload={"tool": "list_dir", "args": {"path": "."}},
    )
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "pass"


def test_self_check_allows_varying_old_string_on_code_edit_retry(
    memory: MemoryStores,
) -> None:
    """Retry edits may change old_string/new_string without contradiction."""
    prior = _entry(
        decision_id="d-old",
        kind="code_edit",
        payload={"old_string": "return 1", "new_string": "return 2"},
    )
    memory.decisions.append(prior)
    proposal = _entry(
        decision_id="d-new",
        kind="code_edit",
        payload={"old_string": "return 2", "new_string": "return 3"},
    )
    result = self_check(proposal, memory, "sess-sc")
    assert result.verdict == "pass"

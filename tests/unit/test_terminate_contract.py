"""Unit tests for typed terminate payload and SessionOutcome.user_message."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from framework.control.models import (
    TerminatePayload,
    parse_terminate_payload,
    user_message_from_payload,
)
from framework.control.self_check import self_check
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord
from framework.orchestration.session import (
    SessionOutcome,
    _session_user_message_from_decisions,
)


def test_terminate_payload_defaults_empty() -> None:
    """TerminatePayload accepts an empty payload for benchmark mode."""
    parsed = parse_terminate_payload({})
    assert parsed.user_message == ""
    assert parsed.turn_type is None


def test_terminate_payload_accepts_answer_alias() -> None:
    """Legacy answer key maps to user_message."""
    parsed = parse_terminate_payload({"answer": "hello", "turn_type": "answer"})
    assert parsed.user_message == "hello"
    assert parsed.turn_type == "answer"


def test_terminate_payload_accepts_all_turn_types() -> None:
    """Each declared turn_type literal validates."""
    for turn_type in ("answer", "inspect", "edit", "build"):
        parsed = TerminatePayload(user_message="ok", turn_type=turn_type)
        assert parsed.turn_type == turn_type


def test_terminate_payload_rejects_invalid_turn_type() -> None:
    """Unknown turn_type values fail schema validation."""
    with pytest.raises(ValidationError):
        TerminatePayload(user_message="x", turn_type="chat")  # type: ignore[arg-type]


def test_user_message_from_payload_prefers_user_message() -> None:
    """user_message wins over legacy answer alias when both are present."""
    msg = user_message_from_payload(
        {"user_message": "typed", "answer": "legacy"},
    )
    assert msg == "typed"


def test_user_message_from_payload_falls_back_to_rationale() -> None:
    """Executor path may fall back to rationale when payload has no message."""
    msg = user_message_from_payload({}, fallback_rationale="from rationale")
    assert msg == "from rationale"


def test_session_outcome_has_user_message_field() -> None:
    """SessionOutcome exposes user_message with empty default."""
    outcome = SessionOutcome(session_id="s1")
    assert outcome.user_message == ""


def test_session_user_message_from_decisions_last_terminate(tmp_path) -> None:
    """Session helper returns user_message from the last terminate decision."""
    memory = MemoryStores(SQLiteBackend(tmp_path / "term.db"))
    session_id = "sess-term"
    memory.decisions.append(
        DecisionEntry(
            session_id=session_id,
            decision_id="d-1",
            step_index=0,
            by_agent="executor",
            kind="terminate",
            payload={"user_message": "first"},
            rationale="r1",
            references=[],
            self_check=SelfCheckRecord(verdict="pass", issues=[]),
            timestamp=datetime.now(UTC),
        )
    )
    memory.decisions.append(
        DecisionEntry(
            session_id=session_id,
            decision_id="d-2",
            step_index=1,
            by_agent="executor",
            kind="tool_call",
            payload={"tool": "read_file"},
            rationale="r2",
            references=[],
            self_check=SelfCheckRecord(verdict="pass", issues=[]),
            timestamp=datetime.now(UTC),
        )
    )
    memory.decisions.append(
        DecisionEntry(
            session_id=session_id,
            decision_id="d-3",
            step_index=2,
            by_agent="executor",
            kind="terminate",
            payload={"user_message": "final reply", "turn_type": "answer"},
            rationale="r3",
            references=[],
            self_check=SelfCheckRecord(verdict="pass", issues=[]),
            timestamp=datetime.now(UTC),
        )
    )
    assert _session_user_message_from_decisions(memory, session_id) == "final reply"


def test_session_user_message_ignores_rationale_without_payload(tmp_path) -> None:
    """Benchmark terminate without user_message stays empty on SessionOutcome."""
    memory = MemoryStores(SQLiteBackend(tmp_path / "bench.db"))
    session_id = "sess-bench"
    memory.decisions.append(
        DecisionEntry(
            session_id=session_id,
            decision_id="d-1",
            step_index=0,
            by_agent="planner",
            kind="terminate",
            payload={},
            rationale="internal only",
            references=[],
            self_check=SelfCheckRecord(verdict="pass", issues=[]),
            timestamp=datetime.now(UTC),
        )
    )
    assert _session_user_message_from_decisions(memory, session_id) == ""


def test_self_check_rejects_invalid_terminate_turn_type(tmp_path) -> None:
    """Self-check fails terminate proposals with invalid turn_type."""
    memory = MemoryStores(SQLiteBackend(tmp_path / "sc.db"))
    session_id = "sess-sc"
    proposal = DecisionEntry(
        session_id=session_id,
        decision_id="d-bad",
        step_index=0,
        by_agent="executor",
        kind="terminate",
        payload={"user_message": "hi", "turn_type": "unknown"},
        rationale="because test",
        references=[],
        self_check=SelfCheckRecord(verdict="fail", issues=[]),
        timestamp=datetime.now(UTC),
    )
    check = self_check(proposal, memory, session_id)
    assert check.verdict == "fail"
    assert any(issue.kind == "schema_violation" for issue in check.issues)

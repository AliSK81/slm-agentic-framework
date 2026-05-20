"""Aviona conversational intent unit tests."""

from __future__ import annotations

from datetime import UTC, datetime

from aviona.contract import TurnContractResult, TurnFileObs, verify_turn
from aviona.intent import conversational_reply, is_conversational
from framework.memory.stores import DecisionEntry, SelfCheckRecord
from framework.orchestration.session import SessionOutcome


def _terminate_entry(answer: str) -> DecisionEntry:
    return DecisionEntry(
        session_id="s1",
        decision_id="d1",
        step_index=0,
        by_agent="executor",
        kind="terminate",
        payload={"user_message": answer, "turn_type": "answer"},
        rationale=answer,
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


def test_greetings_are_conversational() -> None:
    """Greetings and acknowledgments should not invoke the file agent."""
    assert is_conversational("hi")
    assert is_conversational("Hello!")
    assert is_conversational("ok")
    assert is_conversational("OK!")
    assert is_conversational("sure")
    assert not is_conversational("create hello.txt")


def test_answer_turn_accepts_typed_user_message() -> None:
    """Answer contract passes on typed terminate user_message without writes."""
    outcome = SessionOutcome(
        session_id="s1",
        user_message="Provider deepseek, model deepseek-v4-flash.",
        outcome="solved",
    )
    result = verify_turn("answer", outcome, TurnFileObs())
    assert result == TurnContractResult(passed=True)
    assert "deepseek" in outcome.user_message.lower()


def test_answer_turn_fails_without_user_message() -> None:
    """Empty user_message fails the answer contract."""
    outcome = SessionOutcome(session_id="s1", user_message="")
    result = verify_turn("answer", outcome, TurnFileObs())
    assert not result.passed


def test_inspect_turn_rejects_unsolicited_writes() -> None:
    """Inspect contract fails when files were written."""
    outcome = SessionOutcome(session_id="s1", user_message="listed files")
    result = verify_turn(
        "inspect",
        outcome,
        TurnFileObs(changed_paths=["notes.txt"]),
    )
    assert not result.passed


def test_conversational_reply_mentions_explain() -> None:
    """Greeting reply mentions explain capability."""
    reply = conversational_reply("hi")
    assert "explain" in reply.lower()


def test_declared_answer_from_terminate_entry() -> None:
    """Terminate decisions carry user_message used by TurnContract."""
    entry = _terminate_entry("salam")
    assert entry.payload["user_message"] == "salam"

"""Contract-based journey invariants (replaces phrasing-regex journeys)."""

from __future__ import annotations

from datetime import UTC, datetime

from aviona.contract import TurnFileObs, verify_turn
from aviona.turn_io import declared_turn_type
from framework.memory.stores import DecisionEntry, SelfCheckRecord
from framework.orchestration.session import SessionOutcome


def _entry(kind: str, payload: dict) -> DecisionEntry:
    return DecisionEntry(
        session_id="s1",
        decision_id=f"d-{kind}",
        step_index=0,
        by_agent="executor",
        kind=kind,  # type: ignore[arg-type]
        payload=payload,
        rationale="because test",
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


def test_edit_journey_requires_message_write_and_verify() -> None:
    """Edit turn: user_message + file change + verify passed."""
    entries = [
        _entry("tool_call", {"tool": "write_file", "file_path": "foo.txt"}),
        _entry(
            "terminate",
            {"user_message": "Created foo.txt.", "turn_type": "edit"},
        ),
    ]
    outcome = SessionOutcome(
        session_id="s1",
        user_message="Created foo.txt.",
        outcome="solved",
        test_passed=True,
    )
    turn_type = declared_turn_type(entries, file_changes=["foo.txt"])
    result = verify_turn(
        turn_type,
        outcome,
        TurnFileObs(changed_paths=["foo.txt"], verify_passed=True),
    )
    assert result.passed


def test_inspect_journey_read_only_with_message() -> None:
    """Inspect turn passes with message and no writes."""
    entries = [
        _entry("tool_call", {"tool": "read_file", "file_path": "hello.txt"}),
        _entry(
            "terminate",
            {"user_message": "hi", "turn_type": "inspect"},
        ),
    ]
    outcome = SessionOutcome(session_id="s1", user_message="hi", outcome="solved")
    turn_type = declared_turn_type(entries, file_changes=[])
    result = verify_turn(
        turn_type,
        outcome,
        TurnFileObs(changed_paths=[], verify_passed=False),
    )
    assert result.passed


def test_build_journey_needs_plan_handoff() -> None:
    """Build turn type is declared via needs_plan handoff."""
    entries = [_entry("handoff", {"reason": "needs_plan"})]
    assert declared_turn_type(entries, file_changes=[]) == "build"


def test_answer_journey_no_edits() -> None:
    """Answer turn fails when an unsolicited edit occurs."""
    outcome = SessionOutcome(session_id="s1", user_message="ok", outcome="solved")
    result = verify_turn(
        "answer",
        outcome,
        TurnFileObs(changed_paths=["notes.txt"]),
    )
    assert not result.passed

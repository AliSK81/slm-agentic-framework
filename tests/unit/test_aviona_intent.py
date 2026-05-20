"""Aviona conversational intent unit tests."""

from __future__ import annotations

from datetime import UTC, datetime

from aviona.effects import analyze_turn_effects, classify_goal
from aviona.intent import conversational_reply, is_conversational
from framework.memory.stores import DecisionEntry, SelfCheckRecord


def test_greetings_are_conversational() -> None:
    """Greetings and acknowledgments should not invoke the file agent."""
    assert is_conversational("hi")
    assert is_conversational("Hello!")
    assert is_conversational("ok")
    assert is_conversational("OK!")
    assert is_conversational("sure")
    assert not is_conversational("create hello.txt")


def test_codebase_questions_use_explain_or_read_content() -> None:
    """Explain vs read-content vs general classification."""
    assert not is_conversational("explain the codebase")
    assert classify_goal("explain the codebase") == "explain"
    assert classify_goal("what is content of hello file?") == "read_content"
    assert classify_goal("what is your model?") == "general"
    assert classify_goal("what language model?") == "general"


def test_general_question_accepts_terminate_answer() -> None:
    """General Q&A succeeds when the agent terminates with an answer."""
    effects = analyze_turn_effects(
        goal="what is your model?",
        new_entries=[
            DecisionEntry(
                session_id="s1",
                decision_id="d1",
                step_index=0,
                by_agent="executor",
                kind="terminate",
                payload={
                    "answer": "Provider deepseek, model deepseek-v4-flash per runtime anchor."
                },
                rationale="Provider deepseek, model deepseek-v4-flash per runtime anchor.",
                references=[],
                self_check=SelfCheckRecord(verdict="pass", issues=[]),
                timestamp=datetime.now(UTC),
            )
        ],
        file_changes=[],
        tool_outputs=[],
    )
    assert effects.satisfied
    assert "deepseek" in (effects.user_detail or "").lower()


def test_requested_reply_salam() -> None:
    """Short verbatim replies must satisfy general goals and show in detail."""
    from aviona.effects import requested_reply_text

    goal = 'try to fastly reply with "salam"'
    assert requested_reply_text(goal) == "salam"
    effects = analyze_turn_effects(
        goal=goal,
        new_entries=[
            DecisionEntry(
                session_id="s1",
                decision_id="d1",
                step_index=0,
                by_agent="executor",
                kind="terminate",
                payload={"answer": "salam"},
                rationale="salam",
                references=[],
                self_check=SelfCheckRecord(verdict="pass", issues=[]),
                timestamp=datetime.now(UTC),
            )
        ],
        file_changes=[],
        tool_outputs=[],
    )
    assert effects.satisfied
    assert effects.user_detail == "salam"


def test_requested_reply_missing_fails() -> None:
    """General reply request without the text must fail, not vacuous ok."""
    effects = analyze_turn_effects(
        goal='reply with "salam"',
        new_entries=[],
        file_changes=[],
        tool_outputs=[],
    )
    assert not effects.satisfied
    assert effects.failure_reason == "no reply"


def test_conversational_reply_mentions_explain() -> None:
    """Greeting reply mentions explain capability."""
    reply = conversational_reply("hi")
    assert "explain" in reply.lower()


def test_explain_goal_requires_answer_not_edits() -> None:
    """Explain turns need an answer and must not edit files."""
    effects = analyze_turn_effects(
        goal="explain the codebase",
        new_entries=[],
        file_changes=["hello.txt"],
        tool_outputs=[],
    )
    assert not effects.satisfied

    ok = analyze_turn_effects(
        goal="explain the codebase",
        new_entries=[],
        file_changes=[],
        tool_outputs=["This repo is a small sample with main.py and AVIONA.md rules."],
    )
    assert ok.satisfied
    assert "main.py" in (ok.user_detail or "")

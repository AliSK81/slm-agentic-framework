"""Unit tests for the single TurnContract verifier (V2-3)."""

from __future__ import annotations

import ast
from pathlib import Path

from aviona.contract import TurnContractResult, TurnFileObs, verify_turn
from framework.orchestration.session import SessionOutcome


def _outcome(
    *,
    user_message: str = "",
    test_passed: bool = False,
) -> SessionOutcome:
    return SessionOutcome(
        session_id="sess-contract",
        user_message=user_message,
        test_passed=test_passed,
    )


def test_answer_passes_with_message_and_no_writes() -> None:
    """Answer turn succeeds with non-empty user_message and zero writes."""
    result = verify_turn(
        "answer",
        _outcome(user_message="I use mock-model."),
        TurnFileObs(changed_paths=[], verify_passed=False),
    )
    assert result == TurnContractResult(passed=True)


def test_answer_fails_without_user_message() -> None:
    """Answer turn fails when user_message is empty."""
    result = verify_turn(
        "answer",
        _outcome(user_message=""),
        TurnFileObs(),
    )
    assert result.passed is False
    assert result.failure_reason == "missing user_message"


def test_answer_fails_when_writes_occurred() -> None:
    """Answer turn fails if the write ledger records file changes."""
    result = verify_turn(
        "answer",
        _outcome(user_message="oops edited"),
        TurnFileObs(changed_paths=["notes.txt"]),
    )
    assert result.passed is False
    assert "must not write" in (result.failure_reason or "")


def test_inspect_passes_read_only_with_message() -> None:
    """Inspect turn requires user_message and no writes."""
    result = verify_turn(
        "inspect",
        _outcome(user_message="README says hello."),
        TurnFileObs(changed_paths=[]),
    )
    assert result.passed is True


def test_inspect_fails_on_unsolicited_edit() -> None:
    """Inspect turn fails when a file was written."""
    result = verify_turn(
        "inspect",
        _outcome(user_message="listed files"),
        TurnFileObs(changed_paths=["foo.txt"]),
    )
    assert result.passed is False


def test_edit_passes_with_message_write_and_verify() -> None:
    """Edit turn requires user_message, a write, and verify passed."""
    result = verify_turn(
        "edit",
        _outcome(user_message="Created foo.txt.", test_passed=True),
        TurnFileObs(changed_paths=["foo.txt"], verify_passed=True),
    )
    assert result.passed is True


def test_edit_fails_without_write() -> None:
    """Edit turn fails when no file change was observed."""
    result = verify_turn(
        "edit",
        _outcome(user_message="done"),
        TurnFileObs(changed_paths=[], verify_passed=True),
    )
    assert result.passed is False
    assert result.failure_reason == "no edit applied"


def test_edit_fails_when_verify_not_passed() -> None:
    """Edit turn fails when workspace verification did not pass."""
    result = verify_turn(
        "edit",
        _outcome(user_message="done", test_passed=False),
        TurnFileObs(changed_paths=["foo.txt"], verify_passed=False),
    )
    assert result.passed is False
    assert result.failure_reason == "verification failed"


def test_build_passes_with_message_and_verify() -> None:
    """Build turn requires user_message and verify passed."""
    result = verify_turn(
        "build",
        _outcome(user_message="Feature shipped.", test_passed=True),
        TurnFileObs(changed_paths=["a.py", "b.py"], verify_passed=True),
    )
    assert result.passed is True


def test_build_fails_without_user_message() -> None:
    """Build turn fails when user_message is missing."""
    result = verify_turn(
        "build",
        _outcome(user_message="", test_passed=True),
        TurnFileObs(verify_passed=True),
    )
    assert result.passed is False


def test_local_passes_with_canned_line() -> None:
    """Local turn passes with a non-empty canned reply and no writes."""
    result = verify_turn(
        "local",
        _outcome(user_message="Hi!"),
        TurnFileObs(),
    )
    assert result.passed is True


def test_local_fails_on_write() -> None:
    """Local turn must not produce file edits."""
    result = verify_turn(
        "local",
        _outcome(user_message="ok"),
        TurnFileObs(changed_paths=["notes.txt"]),
    )
    assert result.passed is False


def test_contract_module_imports_no_effects_or_fallbacks() -> None:
    """TurnContract must not depend on regex NLU or fallback modules."""
    import aviona.contract as contract_mod

    source = Path(contract_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned = ("effects", "fallbacks")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for name in banned:
                    assert name not in alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for name in banned:
                assert name not in node.module

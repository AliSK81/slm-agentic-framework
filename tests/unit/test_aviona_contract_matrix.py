"""Contract acceptance matrix: turn_type × invariants × budget (V2-6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from aviona.budgets import max_cycles_for_turn_type, verify_turn_budget
from aviona.contract import TurnFileObs, TurnType, verify_turn
from aviona.turn_io import declared_turn_type
from framework.memory.stores import DecisionEntry, SelfCheckRecord
from framework.orchestration.session import SessionOutcome


@dataclass(frozen=True)
class ContractMatrixRow:
    """One matrix row: contract expectations plus optional budget cap."""

    row_id: str
    turn_type: TurnType
    user_message: str | None
    changed_paths: list[str]
    verify_passed: bool
    expected_contract_pass: bool
    contract_failure_contains: str | None = None
    llm_calls: int = 1
    budget_cap: int | None = None
    expected_budget_pass: bool | None = None


def _entry(kind: str, payload: dict) -> DecisionEntry:
    return DecisionEntry(
        session_id="mx",
        decision_id=f"d-{kind}",
        step_index=0,
        by_agent="executor",
        kind=kind,  # type: ignore[arg-type]
        payload=payload,
        rationale="matrix row",
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )


CONTRACT_MATRIX: tuple[ContractMatrixRow, ...] = (
    ContractMatrixRow(
        "local-greeting",
        "local",
        "Hi! Ask me about this project.",
        [],
        False,
        True,
        llm_calls=0,
        budget_cap=0,
    ),
    ContractMatrixRow(
        "local-empty",
        "local",
        "",
        [],
        False,
        False,
        contract_failure_contains="empty local reply",
        llm_calls=0,
        budget_cap=0,
    ),
    ContractMatrixRow(
        "local-no-write",
        "local",
        "ok",
        ["notes.txt"],
        False,
        False,
        contract_failure_contains="must not write",
        llm_calls=0,
        budget_cap=0,
    ),
    ContractMatrixRow(
        "answer-ok",
        "answer",
        "The answer is 4.",
        [],
        False,
        True,
        llm_calls=1,
        budget_cap=1,
    ),
    ContractMatrixRow(
        "answer-missing-message",
        "answer",
        "",
        [],
        False,
        False,
        contract_failure_contains="missing user_message",
        llm_calls=1,
        budget_cap=1,
    ),
    ContractMatrixRow(
        "answer-no-unsolicited-edit",
        "answer",
        "Sure.",
        ["notes.txt"],
        False,
        False,
        contract_failure_contains="must not write",
        llm_calls=1,
        budget_cap=1,
    ),
    ContractMatrixRow(
        "answer-budget-exceeded",
        "answer",
        "Too many cycles.",
        [],
        False,
        True,
        llm_calls=2,
        budget_cap=1,
        expected_budget_pass=False,
    ),
    ContractMatrixRow(
        "inspect-read-only",
        "inspect",
        "Project overview from README.",
        [],
        False,
        True,
        llm_calls=3,
        budget_cap=3,
    ),
    ContractMatrixRow(
        "inspect-no-write",
        "inspect",
        "Listed files.",
        ["foo.txt"],
        False,
        False,
        contract_failure_contains="must not write",
        llm_calls=2,
        budget_cap=3,
    ),
    ContractMatrixRow(
        "inspect-budget-exceeded",
        "inspect",
        "Too many reads.",
        [],
        False,
        True,
        llm_calls=4,
        budget_cap=3,
        expected_budget_pass=False,
    ),
    ContractMatrixRow(
        "edit-write-and-verify",
        "edit",
        "Created foo.txt.",
        ["foo.txt"],
        True,
        True,
        llm_calls=2,
        budget_cap=6,
    ),
    ContractMatrixRow(
        "edit-missing-write",
        "edit",
        "Created foo.txt.",
        [],
        True,
        False,
        contract_failure_contains="no edit applied",
        llm_calls=2,
        budget_cap=6,
    ),
    ContractMatrixRow(
        "edit-verify-failed",
        "edit",
        "Created foo.txt.",
        ["foo.txt"],
        False,
        False,
        contract_failure_contains="verification failed",
        llm_calls=2,
        budget_cap=6,
    ),
    ContractMatrixRow(
        "build-planned",
        "build",
        "Scaffold complete.",
        ["src/main.py", "tests/test_main.py"],
        True,
        True,
        llm_calls=10,
        budget_cap=15,
    ),
    ContractMatrixRow(
        "build-missing-message",
        "build",
        "",
        ["src/main.py"],
        True,
        False,
        contract_failure_contains="missing user_message",
        llm_calls=5,
        budget_cap=15,
    ),
    ContractMatrixRow(
        "build-verify-failed",
        "build",
        "Scaffold complete.",
        ["src/main.py"],
        False,
        False,
        contract_failure_contains="verification failed",
        llm_calls=8,
        budget_cap=15,
    ),
)


DECLARED_TYPE_CASES: tuple[tuple[str, list[DecisionEntry], list[str], TurnType], ...] = (
    (
        "terminate-answer",
        [_entry("terminate", {"user_message": "hi", "turn_type": "answer"})],
        [],
        "answer",
    ),
    (
        "terminate-edit",
        [
            _entry("tool_call", {"tool": "write_file", "file_path": "foo.txt"}),
            _entry("terminate", {"user_message": "done", "turn_type": "edit"}),
        ],
        ["foo.txt"],
        "edit",
    ),
    (
        "needs-plan-handoff",
        [_entry("handoff", {"reason": "needs_plan"})],
        [],
        "build",
    ),
    (
        "infer-edit-from-writes",
        [_entry("terminate", {"user_message": "done"})],
        ["foo.txt"],
        "edit",
    ),
)


@pytest.mark.parametrize("row", CONTRACT_MATRIX, ids=lambda row: row.row_id)
def test_contract_matrix_row(row: ContractMatrixRow) -> None:
    """Each matrix row satisfies contract invariants and budget cap."""
    outcome = SessionOutcome(
        session_id="mx",
        user_message=row.user_message or "",
        outcome="solved",
        llm_calls=row.llm_calls,
        step_count=row.llm_calls,
    )
    file_obs = TurnFileObs(
        changed_paths=row.changed_paths,
        verify_passed=row.verify_passed,
    )
    contract = verify_turn(row.turn_type, outcome, file_obs)
    assert contract.passed == row.expected_contract_pass
    if row.contract_failure_contains:
        assert contract.failure_reason is not None
        assert row.contract_failure_contains in contract.failure_reason

    if row.budget_cap is not None:
        assert max_cycles_for_turn_type(row.turn_type) == row.budget_cap
        budget = verify_turn_budget(row.turn_type, outcome)
        if row.expected_budget_pass is None:
            within_cap = row.llm_calls <= row.budget_cap
            assert budget.passed == within_cap
        else:
            assert budget.passed == row.expected_budget_pass
        if not budget.passed:
            assert budget.failure_reason is not None
            assert "budget exceeded" in budget.failure_reason


@pytest.mark.parametrize(
    ("case_id", "entries", "file_changes", "expected"),
    DECLARED_TYPE_CASES,
    ids=[case[0] for case in DECLARED_TYPE_CASES],
)
def test_declared_turn_type_matrix(
    case_id: str,
    entries: list[DecisionEntry],
    file_changes: list[str],
    expected: TurnType,
) -> None:
    """Declared turn_type is read from typed terminate/handoff decisions."""
    _ = case_id
    build_promoted = case_id == "needs-plan-handoff"
    assert (
        declared_turn_type(
            entries,
            file_changes=file_changes,
            build_promoted=build_promoted,
        )
        == expected
    )

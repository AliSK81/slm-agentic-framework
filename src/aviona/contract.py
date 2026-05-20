"""Single product TurnContract verifier for Aviona REPL turns."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from framework.orchestration.session import SessionOutcome

TurnType = Literal["local", "answer", "inspect", "edit", "build"]


class TurnFileObs(BaseModel):
    """Factual file observations for contract checks (write ledger, not regex NLU)."""

    changed_paths: list[str] = Field(default_factory=list)
    verify_passed: bool = False


class TurnContractResult(BaseModel):
    """Pass/fail aligned with what the REPL displays."""

    passed: bool
    failure_reason: str | None = None


def _writes_occurred(file_obs: TurnFileObs) -> bool:
    return bool(file_obs.changed_paths)


def verify_turn(
    turn_type: TurnType,
    outcome: SessionOutcome,
    file_obs: TurnFileObs,
) -> TurnContractResult:
    """Verify a turn against the declared turn type (ROADMAP §2.1).

    Args:
        turn_type: Agent-declared or Python-local turn classification.
        outcome: Framework session outcome carrying ``user_message``.
        file_obs: Observed file writes and verification result for the turn.

    Returns:
        ``TurnContractResult`` — single product pass/fail for the REPL.
    """
    user_message = outcome.user_message.strip()

    if turn_type == "local":
        if not user_message:
            return TurnContractResult(passed=False, failure_reason="empty local reply")
        if _writes_occurred(file_obs):
            return TurnContractResult(
                passed=False,
                failure_reason="local turn must not write files",
            )
        return TurnContractResult(passed=True)

    if turn_type in ("answer", "inspect"):
        if not user_message:
            return TurnContractResult(passed=False, failure_reason="missing user_message")
        if _writes_occurred(file_obs):
            return TurnContractResult(
                passed=False,
                failure_reason=f"{turn_type} turn must not write files",
            )
        return TurnContractResult(passed=True)

    if turn_type == "edit":
        if not user_message:
            return TurnContractResult(passed=False, failure_reason="missing user_message")
        if not _writes_occurred(file_obs):
            return TurnContractResult(passed=False, failure_reason="no edit applied")
        if not file_obs.verify_passed:
            return TurnContractResult(passed=False, failure_reason="verification failed")
        return TurnContractResult(passed=True)

    if turn_type == "build":
        if not user_message:
            return TurnContractResult(passed=False, failure_reason="missing user_message")
        if not file_obs.verify_passed:
            return TurnContractResult(passed=False, failure_reason="verification failed")
        return TurnContractResult(passed=True)

    return TurnContractResult(
        passed=False,
        failure_reason=f"unknown turn_type: {turn_type!r}",
    )

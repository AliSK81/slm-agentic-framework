"""Terse one-line status rendering for the Aviona REPL."""

from __future__ import annotations

from aviona.contract import TurnContractResult
from framework.orchestration.session import SessionOutcome

STATUS_MAX_WIDTH = 72


def render_turn_detail(
    outcome: SessionOutcome,
    contract: TurnContractResult,
) -> str | None:
    """Return verbatim ``user_message`` on pass, or an honest ``!`` failure line."""
    if contract.passed:
        message = outcome.user_message.strip()
        return message or None
    reason = contract.failure_reason or outcome.error or "turn failed"
    return f"! {reason}"


def render_status(
    outcome: SessionOutcome,
    *,
    contract_passed: bool | None = None,
    edited_path: str | None = None,
    max_width: int = STATUS_MAX_WIDTH,
) -> str:
    """Map a session outcome to a single user-facing status line."""
    passed = contract_passed if contract_passed is not None else (
        outcome.test_passed or outcome.outcome == "solved"
    )
    if passed:
        mark = "ok"
    elif outcome.outcome == "escalate":
        mark = "!"
    else:
        mark = "..."

    parts: list[str] = [mark]
    if edited_path:
        parts.append(f"edited {edited_path}")
    parts.append(f"{outcome.step_count} steps")
    if outcome.tokens_total >= 1000:
        parts.append(f"{outcome.tokens_total / 1000:.1f}k tok")
    elif outcome.tokens_total:
        parts.append(f"{outcome.tokens_total} tok")
    if outcome.error and not passed:
        parts.append(outcome.error[:40])

    line = " | ".join(parts)
    if len(line) > max_width:
        return line[: max_width - 3] + "..."
    return line

"""Terse one-line status rendering for the Aviona REPL."""

from __future__ import annotations

from framework.orchestration.session import SessionOutcome

STATUS_MAX_WIDTH = 72


def render_status(
    outcome: SessionOutcome,
    *,
    edited_path: str | None = None,
    max_width: int = STATUS_MAX_WIDTH,
) -> str:
    """Map a session outcome to a single user-facing status line.

    Never includes raw tool output — only outcome, optional file hint, steps, tokens.

    Args:
        outcome: Completed ``run_full_session`` result.
        edited_path: Optional relative path of the primary edited file.
        max_width: Maximum line width (truncated with ellipsis).

    Returns:
        One-line status string for the REPL.
    """
    if outcome.test_passed or outcome.outcome == "solved":
        mark = "✓"
    elif outcome.outcome == "escalate":
        mark = "!"
    else:
        mark = "…"

    parts: list[str] = [mark]
    if edited_path:
        parts.append(f"edited {edited_path}")
    parts.append(f"{outcome.step_count} steps")
    if outcome.tokens_total >= 1000:
        parts.append(f"{outcome.tokens_total / 1000:.1f}k tok")
    elif outcome.tokens_total:
        parts.append(f"{outcome.tokens_total} tok")
    if outcome.error:
        parts.append(outcome.error[:40])

    line = " · ".join(parts)
    if len(line) > max_width:
        return line[: max_width - 1] + "…"
    return line

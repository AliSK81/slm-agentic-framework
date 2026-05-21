"""Per-turn-type cycle caps aligned with framework interactive budgets (FI-1 / AV3-1)."""

from __future__ import annotations

from aviona.contract import TurnContractResult, TurnType
from framework.control.interactive import load_interactive_budgets
from framework.orchestration.session import SessionOutcome

_FRAMEWORK_BUDGETS = load_interactive_budgets()

# Display and contract verification caps — sourced from configs/models.yaml via framework.
TURN_CYCLE_CAPS: dict[TurnType, int] = {
    "local": 0,
    "answer": _FRAMEWORK_BUDGETS["answer"],
    "inspect": _FRAMEWORK_BUDGETS["inspect"],
    "edit": _FRAMEWORK_BUDGETS["edit"],
    "build": _FRAMEWORK_BUDGETS["build"],
}

INTERACTIVE_CYCLE_CEILING = TURN_CYCLE_CAPS["edit"]
BUILD_CYCLE_CEILING = TURN_CYCLE_CAPS["build"]


def max_cycles_for_turn_type(turn_type: TurnType) -> int:
    """Return the LLM cycle cap for a declared turn type."""
    return TURN_CYCLE_CAPS[turn_type]


def is_read_only_turn_type(turn_type: TurnType) -> bool:
    """True when the turn type must not perform file writes."""
    return turn_type in ("local", "answer", "inspect")


def verify_turn_budget(
    turn_type: TurnType,
    outcome: SessionOutcome,
) -> TurnContractResult:
    """Fail when the turn exceeded its declared type cycle cap."""
    cap = max_cycles_for_turn_type(turn_type)
    calls = outcome.step_count if outcome.step_count else outcome.llm_calls
    if calls > cap:
        return TurnContractResult(
            passed=False,
            failure_reason=f"budget exceeded: {calls} LLM cycles > {cap} for {turn_type}",
        )
    return TurnContractResult(passed=True)

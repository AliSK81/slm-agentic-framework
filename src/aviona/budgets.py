"""Per-turn-type cycle and token budgets (ROADMAP §5)."""

from __future__ import annotations

from aviona.contract import TurnContractResult, TurnType
from framework.orchestration.session import SessionOutcome

# LLM cycle caps per declared turn type.
TURN_CYCLE_CAPS: dict[TurnType, int] = {
    "local": 0,
    "answer": 1,
    "inspect": 3,
    "edit": 6,
    "build": 15,
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
    calls = outcome.llm_calls if outcome.llm_calls else outcome.step_count
    if calls > cap:
        return TurnContractResult(
            passed=False,
            failure_reason=f"budget exceeded: {calls} LLM cycles > {cap} for {turn_type}",
        )
    return TurnContractResult(passed=True)

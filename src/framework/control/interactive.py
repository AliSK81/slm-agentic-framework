"""Interactive turn binding: budgets and permissions from agent-declared turn_type."""

from __future__ import annotations

from functools import lru_cache
import yaml

from framework.control.models import InteractiveTurnState, TurnType
from framework.slm.config import models_config_path

_DEFAULT_BUDGETS: dict[TurnType, int] = {
    "answer": 1,
    "inspect": 4,
    "edit": 6,
    "build": 15,
}


def clear_interactive_config_cache() -> None:
    """Drop cached interactive yaml (for tests)."""
    load_interactive_budgets.cache_clear()


@lru_cache(maxsize=1)
def load_interactive_budgets() -> dict[TurnType, int]:
    """Load per-turn-type cycle budgets from ``configs/models.yaml`` interactive section."""
    raw = yaml.safe_load(models_config_path().read_text(encoding="utf-8")) or {}
    section = raw.get("interactive") or {}
    budgets = section.get("budgets") or {}
    result: dict[TurnType, int] = {}
    for key in ("answer", "inspect", "edit", "build"):
        if key in budgets:
            result[key] = int(budgets[key])  # type: ignore[literal-required]
        else:
            result[key] = _DEFAULT_BUDGETS[key]  # type: ignore[literal-required]
    return result


def turn_type_from_payload(payload: dict[str, object] | None) -> TurnType | None:
    """Return a validated turn_type from a proposal payload, if present."""
    if not payload:
        return None
    raw = str(payload.get("turn_type", "")).strip().lower()
    if raw in ("answer", "inspect", "edit", "build"):
        return raw  # type: ignore[return-value]
    return None


def is_read_only_turn_type(turn_type: TurnType) -> bool:
    """True when the declared type must not perform file writes without turn_type on payload."""
    return turn_type in ("answer", "inspect")


def bind_interactive_turn(turn_type: TurnType) -> InteractiveTurnState:
    """Bind framework budget, read-only flag, and phase from a cycle-1 declared turn_type."""
    budgets = load_interactive_budgets()
    return InteractiveTurnState(
        declared_type=turn_type,
        phase="bound",
        max_steps=budgets[turn_type],
        read_only=is_read_only_turn_type(turn_type),
        bound=True,
    )


def declaring_interactive_turn_state() -> InteractiveTurnState:
    """Initial state before cycle-1 turn_type is declared (single declare cycle)."""
    return InteractiveTurnState(
        declared_type=None,
        phase="declaring",
        max_steps=1,
        read_only=True,
        bound=False,
    )

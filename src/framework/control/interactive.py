"""Interactive turn binding, budgets, and Interactive Completion Protocol (ICP)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from framework.control.models import InteractiveTurnState, TurnType
from framework.memory.stores import DecisionEntry, Issue
from framework.slm.config import models_config_path

IcpPhase = Literal["gather", "must_finalize_or_continue"]

_TOOL_ALIASES: dict[str, str] = {
    "run_terminal_cmd": "shell",
}

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


class InteractiveCompletionState(BaseModel):
    """Python-enforced ICP sub-state for one interactive turn (FI-3)."""

    phase: IcpPhase = "gather"
    tools_used: list[str] = Field(default_factory=list)
    after_edit: bool = False


def _resolve_tool_name(payload: dict[str, object]) -> str:
    """Resolve tool name from alternate SLM payload keys."""
    for key in ("tool", "name", "function", "command"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            raw = value.strip().lower()
            return _TOOL_ALIASES.get(raw, raw)
    return ""


def tool_path_key(tool: str, payload: dict[str, object]) -> str:
    """Stable ``tool:path`` key for repeat-tool deduplication."""
    path = str(payload.get("file_path") or payload.get("path") or "").strip()
    if path:
        return f"{tool}:{path}"
    return tool


def icp_initial_state() -> InteractiveCompletionState:
    """Fresh ICP state at the start of an interactive turn."""
    return InteractiveCompletionState()


def icp_after_successful_tool(
    icp: InteractiveCompletionState,
    tool_key: str,
) -> InteractiveCompletionState:
    """Transition to MUST_FINALIZE after a successful tool call."""
    used = list(icp.tools_used)
    if tool_key and tool_key not in used:
        used.append(tool_key)
    return icp.model_copy(
        update={
            "phase": "must_finalize_or_continue",
            "tools_used": used,
            "after_edit": False,
        }
    )


def icp_after_successful_edit(icp: InteractiveCompletionState) -> InteractiveCompletionState:
    """Require terminate on the next proposal after a successful code_edit."""
    return icp.model_copy(
        update={
            "phase": "must_finalize_or_continue",
            "after_edit": True,
        }
    )


def icp_issues(
    proposal: DecisionEntry,
    icp: InteractiveCompletionState | None,
) -> list[Issue]:
    """ICP self-check rules: mandatory terminate and repeat-tool rejection."""
    if icp is None:
        return []
    issues: list[Issue] = []
    if icp.after_edit and proposal.kind != "terminate":
        issues.append(
            Issue(
                kind="must_terminate_after_edit",
                detail=(
                    "After code_edit you must terminate{user_message, turn_type:edit} "
                    "— no further tools or edits."
                ),
            )
        )
        return issues

    if icp.phase != "must_finalize_or_continue":
        return issues

    if proposal.kind == "terminate":
        return issues

    if proposal.kind == "tool_call":
        payload = proposal.payload or {}
        tool = _resolve_tool_name(payload)
        key = tool_path_key(tool, payload)
        if key in icp.tools_used:
            issues.append(
                Issue(
                    kind="repeat_tool",
                    detail=f"repeat tool {key!r} — terminate or use a different tool/path",
                )
            )
        return issues

    issues.append(
        Issue(
            kind="must_terminate_after_tool",
            detail=(
                "After a successful tool call you must terminate{user_message, turn_type} "
                "or call a new tool (different tool:path)."
            ),
        )
    )
    return issues

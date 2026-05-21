"""FI-6: every tool named in interactive hints is implemented in the executor."""

from __future__ import annotations

import re

from aviona.runtime import interactive_turn_contract_hint
from framework.control.cycle import _EXECUTOR_PAYLOAD_HINT
from framework.orchestration.executor import EXECUTOR_IMPLEMENTED_TOOLS


def _tools_mentioned_in_hint(text: str) -> set[str]:
    """Extract tool identifiers from hint prose (lowercase)."""
    found: set[str] = set()
    for match in re.finditer(
        r"\b(list_dir|read_file|glob|code_edit|pytest|shell|write_file|edit_file)\b",
        text,
        flags=re.IGNORECASE,
    ):
        found.add(match.group(1).lower())
    return found


def test_cycle_executor_hint_tools_are_implemented() -> None:
    """Cycle executor payload hint must not reference missing tools."""
    mentioned = _tools_mentioned_in_hint(_EXECUTOR_PAYLOAD_HINT)
    missing = mentioned - EXECUTOR_IMPLEMENTED_TOOLS
    assert not missing, f"hint references unimplemented tools: {sorted(missing)}"


def test_aviona_interactive_contract_hint_tools_are_implemented() -> None:
    """Aviona interactive contract hint must not reference missing tools."""
    mentioned = _tools_mentioned_in_hint(interactive_turn_contract_hint())
    missing = mentioned - EXECUTOR_IMPLEMENTED_TOOLS
    assert not missing, f"hint references unimplemented tools: {sorted(missing)}"


def test_search_codebase_not_advertised_in_hints() -> None:
    """search_codebase stays out of hints until the executor implements it."""
    combined = _EXECUTOR_PAYLOAD_HINT + interactive_turn_contract_hint()
    assert "search_codebase" not in combined.lower()

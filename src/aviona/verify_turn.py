"""Aviona turn verification — require visible effects, not vacuous compile pass."""

from __future__ import annotations

from pathlib import Path

from aviona.effects import TurnEffects, analyze_turn_effects, changed_files, snapshot_files
from framework.memory.stores import MemoryStores
from framework.orchestration.verify import EvaluationResult, Verifier


class TurnOutcomeVerifier:
    """Wrap a base verifier and fail when the turn produced no useful work."""

    def __init__(
        self,
        inner: Verifier,
        *,
        memory: MemoryStores,
        session_id: str,
        before_ids: frozenset[str],
        goal: str,
        before_files: dict[str, float],
        tool_outputs: list[str],
    ) -> None:
        self._inner = inner
        self._memory = memory
        self._session_id = session_id
        self._before_ids = before_ids
        self._goal = goal
        self._before_files = before_files
        self._tool_outputs = tool_outputs
        self.last_effects: TurnEffects | None = None

    def evaluate(self, workspace: Path) -> EvaluationResult:
        """Run inner verification, then require turn effects for action goals."""
        inner = self._inner.evaluate(workspace)
        if not inner.passed:
            return inner

        file_changes = changed_files(
            self._before_files,
            snapshot_files(workspace),
        )
        new_entries = [
            entry
            for entry in self._memory.decisions.list_for_session(self._session_id)
            if entry.decision_id not in self._before_ids
        ]
        effects = analyze_turn_effects(
            goal=self._goal,
            new_entries=new_entries,
            file_changes=file_changes,
            tool_outputs=self._tool_outputs,
        )
        self.last_effects = effects
        if effects.satisfied:
            return inner
        return EvaluationResult(
            passed=False,
            error_message=effects.failure_reason or "no changes completed",
        )

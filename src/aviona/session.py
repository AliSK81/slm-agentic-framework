"""Aviona session driver — one bounded turn over ``run_full_session``."""

from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import BaseModel

from aviona.project import load_project_rules
from aviona.store import SessionStore, aviona_project_dir, project_hash
from framework.control.ablation import AblationSettings
from framework.memory.stores import MemoryStores
from framework.orchestration.session import SessionOutcome, run_full_session
from framework.orchestration.verify import NoOpVerifier, Verifier

__all__ = ["AvionaSession", "TurnResult", "aviona_project_dir", "project_hash"]


class TurnResult(BaseModel):
    """Concise outcome of one Aviona REPL line."""

    status: str
    outcome: str
    test_passed: bool = False
    step_count: int = 0
    tokens_total: int = 0
    error: str | None = None
    session_id: str = ""


class AvionaSession:
    """cwd-rooted session sharing persistent memory across REPL turns."""

    def __init__(self, cwd: Path) -> None:
        self.workspace = cwd.resolve()
        self.session_root = aviona_project_dir(self.workspace)
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir = self.session_root / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        db_path = self.session_root / "memory.db"
        self.memory = MemoryStores.sqlite(db_path)
        self._session_id = f"aviona-{uuid.uuid4().hex[:8]}"
        self._verifier: Verifier = NoOpVerifier()
        self._project_rules = load_project_rules(self.workspace)
        self._store = SessionStore(self.workspace, self._session_id)

    def run_turn(
        self,
        text: str,
        *,
        constraints: list[str] | None = None,
        verifier: Verifier | None = None,
        max_steps: int = 15,
    ) -> TurnResult:
        """Run one user line through the thesis graph engine.

        Args:
            text: User goal for this turn.
            constraints: Optional hard constraints appended to the anchor.
            verifier: Override verification (default ``NoOpVerifier``).
            max_steps: Step budget for ``run_full_session``.

        Returns:
            ``TurnResult`` with a one-line-friendly status string.
        """
        goal = text.strip()
        before_ids = {
            entry.decision_id
            for entry in self.memory.decisions.list_for_session(self._session_id)
        }
        hard_constraints = list(self._project_rules)
        if constraints:
            hard_constraints.extend(constraints)
        effective = verifier or self._verifier
        session_outcome: SessionOutcome = run_full_session(
            goal,
            hard_constraints,
            workspace=self.workspace,
            memory=self.memory,
            session_id=self._session_id,
            checkpoint_dir=self.checkpoint_dir,
            ablation=AblationSettings(memory=True, control=True, error_control=True),
            engine="graph",
            probe=False,
            verifier=effective,
            planner_enabled=True,
            max_steps=max_steps,
        )
        status = _status_line(session_outcome)
        after_entries = self.memory.decisions.list_for_session(self._session_id)
        new_refs = [
            entry.decision_id
            for entry in after_entries
            if entry.decision_id not in before_ids
        ]
        self._store.append_turn(
            user_text=goal,
            status=status,
            outcome=session_outcome.outcome,
            tokens_total=session_outcome.tokens_total,
            decision_refs=new_refs,
        )
        return TurnResult(
            status=status,
            outcome=session_outcome.outcome,
            test_passed=session_outcome.test_passed,
            step_count=session_outcome.step_count,
            tokens_total=session_outcome.tokens_total,
            error=session_outcome.error,
            session_id=session_outcome.session_id,
        )


def _status_line(outcome: SessionOutcome) -> str:
    if outcome.test_passed or outcome.outcome == "solved":
        label = "ok"
    elif outcome.outcome == "escalate":
        label = "escalate"
    else:
        label = outcome.outcome
    parts = [label, f"{outcome.step_count} steps"]
    if outcome.tokens_total:
        parts.append(f"{outcome.tokens_total} tok")
    if outcome.error:
        parts.append(outcome.error[:80])
    return " · ".join(parts)

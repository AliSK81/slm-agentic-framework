"""Aviona session driver — one bounded turn over ``run_full_session``."""

from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import BaseModel

from aviona.compaction import HistoryBlock, compact, history_to_constraint
from aviona.profiles import apply_daily_driver_profiles
from aviona.project import load_project_rules
from aviona.render import render_status
from aviona.store import SessionStore, aviona_project_dir, project_hash
from framework.control.ablation import AblationSettings
from framework.error_control.truncation import get_compaction_ceiling, set_caps_profile
from framework.memory.stores import DecisionEntry, MemoryStores
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
        apply_daily_driver_profiles()
        set_caps_profile("interactive")
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
        self._context_ceiling = get_compaction_ceiling()
        anchor_text = f"workspace: {self.workspace}"
        if self._project_rules:
            anchor_text = anchor_text + "\n" + self._project_rules[0]
        self._history: list[HistoryBlock] = [
            HistoryBlock(kind="anchor", text=anchor_text),
        ]

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
        self._history = compact(self._history, self._context_ceiling)
        before_ids = {
            entry.decision_id
            for entry in self.memory.decisions.list_for_session(self._session_id)
        }
        hard_constraints = list(self._project_rules)
        context_segment = history_to_constraint(self._history)
        if context_segment:
            hard_constraints.append(context_segment)
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
        after_entries = self.memory.decisions.list_for_session(self._session_id)
        edited_path = _last_edited_path(after_entries)
        status = render_status(session_outcome, edited_path=edited_path)
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
        self._history.append(
            HistoryBlock(
                kind="turn",
                text=f"user: {goal}\nstatus: {status}",
            )
        )
        for entry in after_entries:
            if entry.decision_id not in before_ids:
                tool_text = _decision_tool_text(entry)
                if tool_text:
                    self._history.append(
                        HistoryBlock(kind="tool_output", text=tool_text)
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


def _decision_tool_text(entry: DecisionEntry) -> str | None:
    """Extract a compact tool-output line from a decision entry."""
    if entry.kind == "tool_call":
        tool = entry.payload.get("tool", "tool")
        return f"{tool}: {entry.rationale}"
    if entry.kind == "code_edit":
        path = entry.payload.get("file_path") or entry.payload.get("path") or "file"
        return f"code_edit {path}: {entry.rationale}"
    return None


def _last_edited_path(entries: list[DecisionEntry]) -> str | None:
    """Return the most recent code_edit file_path from decision payloads."""
    for entry in reversed(entries):
        if entry.kind != "code_edit":
            continue
        payload = entry.payload or {}
        path = payload.get("file_path") or payload.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()
    return None

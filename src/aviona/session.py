"""Aviona session driver — one bounded interactive turn per REPL line."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from aviona.budgets import (
    BUILD_CYCLE_CEILING,
    INTERACTIVE_CYCLE_CEILING,
    verify_turn_budget,
)
from aviona.compaction import HistoryBlock, anchor_to_constraint, compact, history_to_constraint
from aviona.contract import TurnFileObs, verify_turn
from aviona.gitctx import git_anchor_segment, git_status
from aviona.permissions import Mode, PermissionAction, PermissionGate
from aviona.profiles import apply_daily_driver_profiles
from aviona.project import load_project_rules
from aviona.render import render_status, render_turn_detail
from aviona.runtime import runtime_anchor_segment, runtime_answer_constraint
from aviona.settings import load_settings
from aviona.snapshots import SnapshotStore
from aviona.store import (
    SessionStore,
    aviona_project_dir,
    fork_session,
    load_session,
    project_hash,
)
from aviona.tools import bind_snapshot_tools
from aviona.turn_io import changed_paths_for_turn, declared_turn_type, snapshot_files
from framework.control.ablation import AblationSettings
from framework.error_control.truncation import get_compaction_ceiling, set_caps_profile
from framework.memory.stores import MemoryStores
from framework.orchestration.session import SessionOutcome, run_turn as framework_run_turn
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
    detail: str | None = None
    session_id: str = ""
    checkpoint_path: str | None = None


class AvionaSession:
    """cwd-rooted session sharing persistent memory across REPL turns."""

    def __init__(
        self,
        cwd: Path,
        *,
        session_id: str | None = None,
        fork_from: str | None = None,
    ) -> None:
        apply_daily_driver_profiles()
        set_caps_profile("interactive")
        self.workspace = cwd.resolve()
        self.session_root = aviona_project_dir(self.workspace)
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir = self.session_root / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        if fork_from is not None:
            record = fork_session(self.workspace, fork_from)
            self._session_id = record.session_id
        elif session_id is not None:
            record = load_session(self.workspace, session_id)
            self._session_id = record.session_id
        else:
            self._session_id = f"aviona-{uuid.uuid4().hex[:8]}"

        db_path = self.session_root / "memory.db"
        self.memory = MemoryStores.sqlite(db_path)
        self._verifier: Verifier = NoOpVerifier()
        self._project_rules = load_project_rules(self.workspace)
        self._store = SessionStore(self.workspace, self._session_id)
        settings = load_settings(self.workspace)
        self.permission_gate = PermissionGate(
            mode=settings.mode,
            allowlist=settings.commands,
        )
        self._context_ceiling = get_compaction_ceiling()
        self.git_status = git_status(self.workspace)
        anchor_text = f"workspace: {self.workspace}"
        git_seg = git_anchor_segment(self.git_status)
        if git_seg:
            anchor_text = anchor_text + "\n" + git_seg
        if self._project_rules:
            anchor_text = anchor_text + "\n" + self._project_rules[0]
        anchor_text = anchor_text + "\n" + runtime_anchor_segment(cwd=self.workspace)
        self._history: list[HistoryBlock] = [
            HistoryBlock(kind="anchor", text=anchor_text),
        ]
        self.snapshots = SnapshotStore(self.workspace, store_root=self.session_root)
        self._write_file_fn, self._edit_file_fn = bind_snapshot_tools(
            self.snapshots,
            self.workspace,
        )
        self._last_checkpoint_path: str | None = None

    def undo_last(self) -> list[str]:
        """Restore files snapshotted before the last turn's mutations."""
        return self.snapshots.undo_last()

    def set_mode(self, mode: Mode) -> None:
        """Switch permission mode for subsequent turns."""
        self.permission_gate.set_mode(mode)

    def set_confirm_reader(self, reader: Callable[[str], str]) -> None:
        """Wire REPL ``reader`` for permission prompts (``ask`` verdict)."""
        self.permission_gate.set_confirm(
            lambda prompt: reader(prompt).strip().lower() in ("y", "yes")
        )

    def _permission_check(self, kind: str, detail: str) -> bool:
        if kind not in ("write_file", "edit_file", "shell"):
            return True
        return self.permission_gate.ensure(
            PermissionAction(kind=kind, detail=detail)  # type: ignore[arg-type]
        )

    def _build_turn_constraints(
        self,
        *,
        extra: list[str] | None = None,
    ) -> list[str]:
        """Assemble anchor-first hard constraints for one interactive turn."""
        hard_constraints: list[str] = []
        anchor = anchor_to_constraint(self._history)
        if anchor:
            hard_constraints.append(anchor)
        hard_constraints.append(runtime_answer_constraint())
        context_segment = history_to_constraint(self._history)
        if context_segment:
            hard_constraints.append(context_segment)
        if extra:
            hard_constraints.extend(extra)
        return hard_constraints

    def run_turn(
        self,
        text: str,
        *,
        constraints: list[str] | None = None,
        verifier: Verifier | None = None,
        max_steps: int = 15,
    ) -> TurnResult:
        """Run one user line: anchor → interactive engine → TurnContract → render.

        Args:
            text: User goal for this turn.
            constraints: Optional hard constraints appended to the anchor.
            verifier: Override verification (default ``NoOpVerifier``).
            max_steps: Step budget for the framework interactive turn.

        Returns:
            ``TurnResult`` with status line and typed ``user_message`` detail.
        """
        goal = text.strip()
        self._history = compact(self._history, self._context_ceiling)
        before_ids = {
            entry.decision_id
            for entry in self.memory.decisions.list_for_session(self._session_id)
        }
        before_files = snapshot_files(self.workspace)
        hard_constraints = self._build_turn_constraints(extra=constraints)
        effective = verifier or self._verifier

        self.snapshots.begin_turn()
        try:
            session_outcome: SessionOutcome = framework_run_turn(
                goal,
                hard_constraints,
                self.workspace,
                memory=self.memory,
                session_id=self._session_id,
                checkpoint_dir=self.checkpoint_dir,
                ablation=AblationSettings(memory=True, control=True, error_control=True),
                probe=False,
                verifier=effective,
                max_steps=INTERACTIVE_CYCLE_CEILING,
                permission_check=self._permission_check,
                write_file_fn=self._write_file_fn,
                edit_file_fn=self._edit_file_fn,
                interactive_read_only=True,
                build_max_steps=BUILD_CYCLE_CEILING,
            )
        finally:
            self.snapshots.end_turn()

        self._last_checkpoint_path = session_outcome.checkpoint_path
        after_entries = [
            entry
            for entry in self.memory.decisions.list_for_session(self._session_id)
            if entry.decision_id not in before_ids
        ]
        file_changes = changed_paths_for_turn(
            before_files,
            snapshot_files(self.workspace),
            after_entries,
        )
        turn_type = declared_turn_type(after_entries, file_changes=file_changes)
        contract = verify_turn(
            turn_type,
            session_outcome,
            TurnFileObs(
                changed_paths=file_changes,
                verify_passed=session_outcome.test_passed,
            ),
        )
        budget = verify_turn_budget(turn_type, session_outcome)
        if not budget.passed:
            contract = budget
        if not contract.passed:
            session_outcome = session_outcome.model_copy(
                update={
                    "outcome": "unresolvable",
                    "test_passed": False,
                    "error": contract.failure_reason,
                }
            )

        status = render_status(session_outcome, contract_passed=contract.passed)
        detail = render_turn_detail(session_outcome, contract)
        new_refs = [entry.decision_id for entry in after_entries]
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
        return TurnResult(
            status=status,
            outcome=session_outcome.outcome,
            test_passed=session_outcome.test_passed,
            step_count=session_outcome.step_count,
            tokens_total=session_outcome.tokens_total,
            error=session_outcome.error,
            detail=detail,
            session_id=session_outcome.session_id,
            checkpoint_path=session_outcome.checkpoint_path,
        )

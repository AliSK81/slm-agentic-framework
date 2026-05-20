"""Aviona session driver — one bounded turn over ``run_full_session``."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from aviona.compaction import HistoryBlock, compact, history_to_constraint
from aviona.effects import (
    TurnEffects,
    analyze_turn_effects,
    changed_files,
    classify_goal,
    infer_target_file,
    is_open_question,
    is_project_question,
    pick_user_detail,
    requested_reply_text,
    snapshot_files,
)
from aviona.runtime import runtime_anchor_segment
from aviona.gitctx import git_anchor_segment, git_status
from aviona.permissions import Mode, PermissionAction, PermissionGate
from aviona.profiles import apply_daily_driver_profiles
from aviona.project import load_project_rules
from aviona.render import render_status
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
from aviona.fallbacks import try_explain_fallback, try_read_content_fallback
from framework.control.ablation import AblationSettings
from framework.error_control.truncation import get_compaction_ceiling, set_caps_profile
from framework.memory.stores import DecisionEntry, MemoryStores
from framework.orchestration.session import SessionOutcome, run_full_session
from framework.orchestration.verify import NoOpVerifier, Verifier

__all__ = ["AvionaSession", "TurnResult", "aviona_project_dir", "project_hash"]

_REVERT_ON_FAILURE = frozenset(
    {
        "no file edit requested",
        "read-only question",
        "read-only request",
    }
)

_AVIONA_EXECUTOR_HINT = (
    "[AVIONA EXECUTOR] Match the user's intent. "
    "File work (create/edit/write): use write_file or code_edit with the exact path. "
    "Listing: tool_call list_dir. Reading: tool_call read_file. "
    "Questions/explain: read-only — list_dir/read_file, then terminate with the full answer in rationale."
)
_AVIONA_READ_HINT = (
    "[AVIONA READ] List directory only. Use tool_call list_dir with path '.'."
)
_AVIONA_READ_CONTENT_HINT = (
    "[AVIONA READ CONTENT] Show file body with read_file on the target path. "
    "Do not use list_dir. Call read_file first, then terminate with the file text."
)
_AVIONA_EXPLAIN_HINT = (
    "[AVIONA EXPLAIN] Read-only turn. Inspect the repo with list_dir and read_file. "
    "Do not create or edit files. Finish with kind terminate and a complete answer in rationale "
    '(optional payload.answer). Minimum two sentences.'
)
_AVIONA_QA_HINT = (
    "[AVIONA Q&A] Answer from runtime facts in the anchor when the question is about Aviona "
    "or the language model. Use terminate with the answer. Do not read repo files unless the "
    "question is about this codebase."
)
_AVIONA_REPLY_HINT = (
    "[AVIONA REPLY] User wants a verbatim text reply. Terminate immediately with kind terminate "
    "and put the exact requested text in payload.answer and rationale. No file tools."
)


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
        anchor_text = anchor_text + "\n" + runtime_anchor_segment()
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

    @staticmethod
    def _read_only_permission_check(
        inner: Callable[[str, str], bool],
    ) -> Callable[[str, str], bool]:
        """Block writes during explain/Q&A turns; allow reads and read-only tools."""

        def check(kind: str, detail: str) -> bool:
            if kind in ("write_file", "edit_file"):
                return False
            if kind == "shell":
                lowered = detail.lower()
                if any(
                    token in lowered
                    for token in (">", ">>", "rm ", "del ", "move ", "copy ", "mkdir ")
                ):
                    return False
            return inner(kind, detail)

        return check

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
        goal_kind = classify_goal(goal)
        self._history = compact(self._history, self._context_ceiling)
        before_ids = {
            entry.decision_id
            for entry in self.memory.decisions.list_for_session(self._session_id)
        }
        before_files = snapshot_files(self.workspace)
        effect_outputs: list[str] = []
        hard_constraints = list(self._project_rules)
        hard_constraints.append(_AVIONA_EXECUTOR_HINT)
        if goal_kind == "read":
            hard_constraints.append(_AVIONA_READ_HINT)
        elif goal_kind == "read_content":
            hard_constraints.append(_AVIONA_READ_CONTENT_HINT)
            target = infer_target_file(goal, self.workspace)
            if target:
                hard_constraints.append(
                    f"[AVIONA TARGET FILE] Required: tool_call read_file with path {target!r}. "
                    "Do not use list_dir for this turn."
                )
        elif goal_kind == "explain":
            hard_constraints.append(_AVIONA_EXPLAIN_HINT)
            if is_project_question(goal):
                hard_constraints.append(
                    "[AVIONA PROJECT QUESTION] Read README.md and main source files, "
                    "then terminate with a multi-sentence project summary in rationale."
                )
        elif goal_kind == "general" and is_open_question(goal):
            hard_constraints.append(_AVIONA_QA_HINT)
        elif goal_kind == "general" and requested_reply_text(goal):
            hard_constraints.append(_AVIONA_REPLY_HINT)
        context_segment = history_to_constraint(self._history)
        if context_segment:
            hard_constraints.append(context_segment)
        if constraints:
            hard_constraints.extend(constraints)
        effective = verifier or self._verifier
        permission = self._permission_check
        if goal_kind in ("explain", "read_content") or requested_reply_text(goal):
            permission = self._read_only_permission_check(permission)
        step_budget = max_steps
        if goal_kind == "general" and (is_open_question(goal) or requested_reply_text(goal)):
            step_budget = min(max_steps, 5)
        self.snapshots.begin_turn()
        try:
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
                max_steps=step_budget,
                permission_check=permission,
                write_file_fn=self._write_file_fn,
                edit_file_fn=self._edit_file_fn,
                effect_sink=effect_outputs,
            )
        finally:
            self.snapshots.end_turn()
        self._last_checkpoint_path = session_outcome.checkpoint_path
        after_entries = self.memory.decisions.list_for_session(self._session_id)
        file_changes = changed_files(before_files, snapshot_files(self.workspace))
        effects = analyze_turn_effects(
            goal=goal,
            new_entries=[
                entry for entry in after_entries if entry.decision_id not in before_ids
            ],
            file_changes=file_changes,
            tool_outputs=effect_outputs,
        )
        if not effects.satisfied:
            fallback: TurnEffects | None = None
            if goal_kind == "read_content":
                fallback = try_read_content_fallback(goal, self.workspace)
            elif goal_kind == "explain" and is_project_question(goal):
                fallback = try_explain_fallback(self.workspace)
            if fallback is not None and fallback.satisfied:
                effects = fallback
                session_outcome = session_outcome.model_copy(
                    update={
                        "outcome": "solved",
                        "test_passed": True,
                        "error": None,
                    }
                )
        if session_outcome.outcome == "solved" and not effects.satisfied:
            session_outcome.outcome = "unresolvable"
            session_outcome.test_passed = False
            session_outcome.error = effects.failure_reason or "no changes completed"

        reverted: list[str] = []
        if (
            not effects.satisfied
            and effects.failure_reason in _REVERT_ON_FAILURE
            and (effects.edited_paths or file_changes)
        ):
            reverted = self.snapshots.undo_last()
            if reverted:
                effects = effects.model_copy(update={"edited_paths": []})

        edited_path: str | None = None
        if effects.satisfied or session_outcome.test_passed:
            edited_path = _last_edited_path(after_entries) or (
                effects.edited_paths[-1] if effects.edited_paths else None
            )
        status = render_status(session_outcome, edited_path=edited_path)
        answer = _best_answer_from_entries(
            [entry for entry in after_entries if entry.decision_id not in before_ids],
            goal=goal,
        )
        detail = pick_user_detail(
            goal_kind,
            tool_outputs=effect_outputs,
            answer=effects.user_detail or answer,
        )
        if reverted:
            undo_note = f"Reverted: {', '.join(reverted)}"
            detail = f"{detail}\n{undo_note}" if detail else undo_note
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


def _best_answer_from_entries(entries: list[DecisionEntry], *, goal: str = "") -> str | None:
    """Extract terminate answer from new decision entries."""
    from aviona.effects import _best_answer

    return _best_answer(entries, [], goal=goal)

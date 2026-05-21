"""Decision Cycle: READ → PROPOSE → SELF_CHECK → CORRECT → ACT → RECORD."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from framework.control.budget import StepBudgetLimiter
from framework.control.models import CycleResult, ErrorControlBundle, SLMProposal
from framework.control.self_check import self_check
from framework.error_control.parser import parse_decision
from framework.memory.stores import DecisionEntry, Issue, MemoryStores, SelfCheckRecord
from framework.memory.working_memory import (
    WorkingMemory,
    WorkingMemoryBudgetError,
    WorkingMemoryBuilder,
)
from framework.control.ablation import AblationSettings
from framework.error_control.quality import QualityResult
from framework.slm.client import ModelProfile, SLMClient

logger = logging.getLogger(__name__)

_FORMAT_BY_ROLE: dict[str, str] = {
    "planner": "plan_step, terminate, handoff",
    "executor": "code_edit, tool_call, terminate, handoff",
}

_EXECUTOR_PAYLOAD_HINT = (
    'For code_edit use file_path "solution.py" unless editing another file. '
    "For existing files, include old_string for partial edits, or send a full "
    'replacement function in content/code/new_string. '
    "You HAVE tools: list_dir (path=.), read_file (file_path), code_edit, shell. "
    "Use them — never claim you lack filesystem access."
)

_TERMINATE_PAYLOAD_HINT = (
    'For terminate include payload "user_message" (exact text shown to the user) '
    'and "turn_type" (one of: answer, inspect, edit, build). '
    "Benchmark/eval tasks may leave user_message empty."
)

_HANDOFF_PAYLOAD_HINT = (
    'For handoff requesting full planning use payload {"reason":"needs_plan"} '
    "only for multi-file build tasks — never for greetings, meta/self questions, "
    "read-only inspect, or single-file edits. Use terminate instead."
)


def _json_format_block(agent_role: str, *, include_example: bool = True) -> str:
    """Append strict JSON instructions so SLMs emit parseable decisions.

    The full example block is omitted when ``include_example`` is False (compact
    corrective rounds after self-check failure).
    """
    kinds = _FORMAT_BY_ROLE.get(agent_role, "terminate")
    hints: list[str] = []
    if agent_role == "executor":
        hints.append(_EXECUTOR_PAYLOAD_HINT)
        hints.append(_TERMINATE_PAYLOAD_HINT)
        hints.append(_HANDOFF_PAYLOAD_HINT)
    elif agent_role == "planner":
        hints.append(_TERMINATE_PAYLOAD_HINT)
    hint = "\n" + "\n".join(hints) if hints else ""
    header = (
        "\n[FORMAT]: Respond with a single JSON object only. "
        "Do not use markdown fences or prose outside the JSON.\n"
        f'Required keys: "kind" (one of: {kinds}), '
        '"rationale" (non-empty string), "payload" (object), '
        '"references" (array of strings, optional).'
    )
    if not include_example:
        return header + hint
    if agent_role == "executor":
        example = (
            'Example: {"kind":"terminate","rationale":"because ...",'
            '"payload":{"user_message":"Here is the answer.","turn_type":"answer"},'
            '"references":[]}\n'
            'Example inspect: {"kind":"tool_call","rationale":"because ...",'
            '"payload":{"tool":"list_dir","path":"."},"references":[]}\n'
            'Example edit: {"kind":"code_edit","rationale":"because ...",'
            '"payload":{"file_path":"foo.txt","new_string":"hi","turn_type":"edit"},'
            '"references":[]}'
        )
    elif agent_role == "planner":
        example = (
            'Example: {"kind":"plan_step","rationale":"because ...",'
            '"payload":{"subtasks":[]},"references":[]}\n'
            'Example terminate: {"kind":"terminate","rationale":"because ...",'
            '"payload":{"user_message":"","turn_type":"build"},"references":[]}'
        )
    else:
        example = (
            'Example: {"kind":"plan_step","rationale":"because ...",'
            '"payload":{"subtasks":[]},"references":[]}'
        )
    return header + "\n" + example + hint


class DecisionCycle:
    """Per-LLM-call control loop for planner and executor agents."""

    def __init__(
        self,
        slm: SLMClient,
        memory: MemoryStores,
        wm_builder: WorkingMemoryBuilder,
        error_control: ErrorControlBundle,
        profile: ModelProfile,
        *,
        max_steps: int = 20,
        ablation: AblationSettings | None = None,
    ) -> None:
        self._slm = slm
        self._memory = memory
        self._wm_builder = wm_builder
        self._error_control = error_control
        self._profile = profile
        self._max_steps = max_steps
        self._ablation = ablation or AblationSettings()

    def _build_corrective_prompt(
        self,
        wm: WorkingMemory,
        issues: list,
        retry_count: int,
        agent_role: str,
        *,
        include_example: bool,
    ) -> list[dict[str, str]]:
        """Prepend anchor prompt and append issue-specific corrective instructions."""
        base = wm.to_prompt_prefix()
        lines = [
            base,
            "",
            f"[CORRECTION RETRY {retry_count}]",
            "Your previous output failed validation. Fix all issues below.",
        ]
        for issue in issues:
            lines.append(f"- [{issue.kind}] {issue.detail}")
        lines.append("Restate all hard constraints from [CONSTRAINTS] in your rationale.")
        content = "\n".join(lines) + _json_format_block(
            agent_role,
            include_example=include_example,
        )
        return [{"role": "user", "content": content}]

    def _proposal_to_entry(
        self,
        proposal: SLMProposal,
        *,
        session_id: str,
        agent_role: str,
        step_index: int,
        check: SelfCheckRecord,
    ) -> DecisionEntry:
        return DecisionEntry(
            session_id=session_id,
            decision_id=f"d-{uuid.uuid4().hex[:8]}",
            step_index=step_index,
            by_agent=agent_role,  # type: ignore[arg-type]
            kind=proposal.kind,
            payload=proposal.payload,
            rationale=proposal.rationale,
            references=proposal.references,
            self_check=check,
            timestamp=datetime.now(UTC),
        )

    def run(
        self,
        session_id: str,
        agent_role: str,
        current_subtask: str,
        subtask_id: str,
        action_fn: Callable[[DecisionEntry], Any],
        max_retries: int = 3,
        *,
        step_count: int = 0,
        max_steps: int | None = None,
        last_error: str | None = None,
        session_retry_count: int = 0,
        decision_floor: int = 0,
    ) -> CycleResult:
        """Execute the full decision cycle; never raises on SLM failure."""
        limiter = StepBudgetLimiter(
            max_steps if max_steps is not None else self._max_steps,
            max_retries,
        )
        if not limiter.check_steps(step_count):
            return CycleResult(budget_exceeded=True)

        retry_count = 0
        wm_retry = max(int(session_retry_count), 0)
        try:
            wm = self._wm_builder.build(
                session_id=session_id,
                agent_role=agent_role,
                current_subtask=current_subtask,
                subtask_id=subtask_id,
                last_error=last_error,
                retry_count=wm_retry,
            )
        except WorkingMemoryBudgetError as exc:
            logger.warning("Working memory budget exceeded: %s", exc)
            return CycleResult(exhausted=True, retry_count=retry_count)
        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": wm.to_prompt_prefix()
                + _json_format_block(agent_role, include_example=True),
            }
        ]

        while retry_count <= max_retries:
            if retry_count > 0 and not limiter.check_retries(retry_count):
                break

            logger.debug(
                "[CYCLE] start agent=%s subtask=%r retry=%d session=%s",
                agent_role,
                current_subtask,
                retry_count,
                session_id,
            )
            response = self._slm.call(messages, role=agent_role, json_mode=True)
            if response.error:
                logger.warning("SLM error in cycle: %s", response.error)
                logger.debug(
                    "[CYCLE] exhausted agent=%s error=%s retry=%d",
                    agent_role,
                    response.error,
                    retry_count,
                )
                return CycleResult(exhausted=True, retry_count=retry_count)

            raw = response.content
            parsed = parse_decision(raw, SLMProposal)
            all_recent = self._memory.decisions.list_for_session(session_id)
            recent = all_recent[decision_floor:] if decision_floor else all_recent
            recent = recent[-10:]
            if self._ablation.error_control:
                quality = self._error_control.quality_gate.check(raw, parsed, recent)
            else:
                quality = QualityResult(
                    passed=parsed is not None and bool(raw.strip()),
                    failure_mode=None if parsed is not None else "unparseable",
                )

            if not quality.passed or parsed is None:
                logger.debug(
                    "[QUALITY] fail agent=%s mode=%s parsed=%s retry=%d",
                    agent_role,
                    quality.failure_mode or "unparseable",
                    parsed.kind if parsed is not None else None,
                    retry_count + 1,
                )
                retry_count += 1
                if retry_count > max_retries:
                    break
                wm = self._wm_builder.build(
                    session_id=session_id,
                    agent_role=agent_role,
                    current_subtask=current_subtask,
                    subtask_id=subtask_id,
                    retry_count=retry_count,
                )
                mode = quality.failure_mode or "unparseable"
                kind: str = "schema_violation" if mode == "unparseable" else "empty"
                issues = [Issue(kind=kind, detail=f"quality gate: {mode}")]  # type: ignore[arg-type]
                messages = self._build_corrective_prompt(
                    wm,
                    issues,
                    retry_count,
                    agent_role,
                    include_example=True,
                )
                continue

            step_index = len(self._memory.decisions.list_for_session(session_id))
            draft = self._proposal_to_entry(
                parsed,
                session_id=session_id,
                agent_role=agent_role,
                step_index=step_index,
                check=SelfCheckRecord(verdict="fail", issues=[]),
            )
            logger.debug(
                "[CYCLE] proposal agent=%s kind=%s turn_type=%s",
                agent_role,
                parsed.kind,
                (parsed.payload or {}).get("turn_type"),
            )
            if self._ablation.control:
                check = self_check(draft, self._memory, session_id)
            else:
                check = SelfCheckRecord(verdict="pass", issues=[])
            draft = draft.model_copy(update={"self_check": check})

            if check.verdict != "pass":
                logger.debug(
                    "[CYCLE] self_check_retry agent=%s kind=%s retry=%d issues=%d",
                    agent_role,
                    parsed.kind,
                    retry_count + 1,
                    len(check.issues),
                )
                retry_count += 1
                if retry_count > max_retries:
                    draft = draft.model_copy(
                        update={
                            "self_check": SelfCheckRecord(
                                verdict="exhausted",
                                issues=check.issues,
                            )
                        }
                    )
                    self._memory.decisions.append(draft)
                    return CycleResult(
                        decision=draft,
                        exhausted=True,
                        retry_count=retry_count,
                    )
                wm = self._wm_builder.build(
                    session_id=session_id,
                    agent_role=agent_role,
                    current_subtask=current_subtask,
                    subtask_id=subtask_id,
                    retry_count=retry_count,
                )
                messages = self._build_corrective_prompt(
                    wm,
                    check.issues,
                    retry_count,
                    agent_role,
                    include_example=False,
                )
                continue

            outcome = action_fn(draft)
            self._memory.decisions.append(draft)
            logger.debug(
                "[CYCLE] complete agent=%s kind=%s decision_id=%s retries=%d",
                agent_role,
                draft.kind,
                draft.decision_id,
                retry_count,
            )
            return CycleResult(
                decision=draft,
                outcome=outcome,
                retry_count=retry_count,
            )

        logger.debug(
            "[CYCLE] exhausted agent=%s retries=%d session=%s",
            agent_role,
            retry_count,
            session_id,
        )
        return CycleResult(exhausted=True, retry_count=retry_count)

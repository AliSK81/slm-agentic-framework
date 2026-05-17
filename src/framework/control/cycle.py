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
from framework.memory.working_memory import WorkingMemory, WorkingMemoryBuilder
from framework.slm.client import ModelProfile, SLMClient

logger = logging.getLogger(__name__)

_FORMAT_BY_ROLE: dict[str, str] = {
    "planner": "plan_step, terminate, handoff",
    "executor": "code_edit, tool_call, terminate, handoff",
}


def _json_format_block(agent_role: str) -> str:
    """Append strict JSON instructions so SLMs emit parseable decisions."""
    kinds = _FORMAT_BY_ROLE.get(agent_role, "terminate")
    return (
        "\n[FORMAT]: Respond with a single JSON object only. "
        "Do not use markdown fences or prose outside the JSON.\n"
        f'Required keys: "kind" (one of: {kinds}), '
        '"rationale" (non-empty string), "payload" (object), '
        '"references" (array of strings, optional).\n'
        'Example: {"kind":"plan_step","rationale":"because ...",'
        '"payload":{"subtasks":[]},"references":[]}'
    )


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
    ) -> None:
        self._slm = slm
        self._memory = memory
        self._wm_builder = wm_builder
        self._error_control = error_control
        self._profile = profile
        self._max_steps = max_steps

    def _build_corrective_prompt(
        self,
        wm: WorkingMemory,
        issues: list,
        retry_count: int,
    ) -> list[dict[str, str]]:
        """Prepend anchor prompt and append issue-specific corrective instructions."""
        base = wm.to_prompt_prefix()
        lines = [
            base,
            "",
            f"[CORRECTION RETRY {retry_count}]",
            "Your previous output failed validation. Fix all issues below.",
            "Respond with strict JSON only.",
        ]
        for issue in issues:
            lines.append(f"- [{issue.kind}] {issue.detail}")
        lines.append("Restate all hard constraints from [CONSTRAINTS] in your rationale.")
        return [{"role": "user", "content": "\n".join(lines)}]

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
    ) -> CycleResult:
        """Execute the full decision cycle; never raises on SLM failure."""
        limiter = StepBudgetLimiter(
            max_steps if max_steps is not None else self._max_steps,
            max_retries,
        )
        if not limiter.check_steps(step_count):
            return CycleResult(budget_exceeded=True)

        retry_count = 0
        wm = self._wm_builder.build(
            session_id=session_id,
            agent_role=agent_role,
            current_subtask=current_subtask,
            subtask_id=subtask_id,
            retry_count=0,
        )
        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": wm.to_prompt_prefix() + _json_format_block(agent_role),
            }
        ]

        while retry_count <= max_retries:
            if retry_count > 0 and not limiter.check_retries(retry_count):
                break

            response = self._slm.call(messages, role=agent_role, json_mode=True)
            if response.error:
                logger.warning("SLM error in cycle: %s", response.error)
                return CycleResult(exhausted=True, retry_count=retry_count)

            raw = response.content
            parsed = parse_decision(raw, SLMProposal)
            recent = self._memory.decisions.get_last_n(session_id, 10)
            quality = self._error_control.quality_gate.check(raw, parsed, recent)

            if not quality.passed or parsed is None:
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
                messages = self._build_corrective_prompt(wm, issues, retry_count)
                continue

            step_index = len(self._memory.decisions.list_for_session(session_id))
            draft = self._proposal_to_entry(
                parsed,
                session_id=session_id,
                agent_role=agent_role,
                step_index=step_index,
                check=SelfCheckRecord(verdict="fail", issues=[]),
            )
            check = self_check(draft, self._memory, session_id)
            draft = draft.model_copy(update={"self_check": check})

            if check.verdict != "pass":
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
                messages = self._build_corrective_prompt(wm, check.issues, retry_count)
                continue

            outcome = action_fn(draft)
            self._memory.decisions.append(draft)
            return CycleResult(
                decision=draft,
                outcome=outcome,
                retry_count=retry_count,
            )

        return CycleResult(exhausted=True, retry_count=retry_count)

"""Working Memory builder — assembles L1 context from L2 stores."""

from __future__ import annotations

import logging

from framework.memory.retrieval import _cap_tokens, retrieve_top_k
from framework.memory.stores import MemoryStores, ToolResultEntry, WorkingMemory
from framework.slm.client import ModelProfile
from framework.slm.skills import select_skill_card

logger = logging.getLogger(__name__)


def _shrink_text(text: str, max_tokens: int) -> str:
    """Cap by word count and by character length (handles single long tokens)."""
    capped = _cap_tokens(text, max_tokens)
    max_chars = max(max_tokens, 1) * 4
    if len(capped) <= max_chars:
        return capped
    return capped[:max_chars]


_AGENT_SCOPES = {
    "planner": "Decompose programming tasks into ordered sub-tasks. Do not write code or invoke tools.",
    "executor": "Implement the current sub-task using bounded tools. Do not change session goal or constraints.",
}


class WorkingMemoryBudgetError(ValueError):
    """Raised when working memory cannot fit even after truncation."""


class WorkingMemoryBuilder:
    """Builds L1 WorkingMemory from L2 stores and model profile."""

    def __init__(
        self,
        memory: MemoryStores,
        profile: ModelProfile,
        *,
        enable_memory: bool = True,
    ) -> None:
        self._memory = memory
        self._profile = profile
        self._enable_memory = enable_memory

    def _fit_to_budget(self, wm: WorkingMemory) -> WorkingMemory:
        """Truncate fields until ``wm`` is within the profile token ceiling."""
        ceiling = self._profile.max_working_memory_tokens
        if wm.token_count() <= ceiling:
            return wm

        logger.warning(
            "Working memory %s tokens exceeds ceiling %s; truncating",
            wm.token_count(),
            ceiling,
        )

        goal = wm.original_goal
        constraints = list(wm.hard_constraints)
        current_subtask = wm.current_subtask
        retrieved = list(wm.retrieved_items)
        tool_results = list(wm.tool_results)
        recent_turn_recap = list(wm.recent_turn_recap)

        constraints = [
            _shrink_text(c, max(8, ceiling // 6)) if len(c) > ceiling * 2 else c
            for c in constraints
        ]
        wm = wm.model_copy(update={"hard_constraints": constraints})

        for _ in range(32):
            if wm.token_count() <= ceiling:
                return wm

            if constraints and max(len(c) for c in constraints) > ceiling * 2:
                constraints = [_shrink_text(c, max(8, ceiling // 8)) for c in constraints]
            elif len(current_subtask) > ceiling * 4 or len(current_subtask.split()) > 40:
                current_subtask = _shrink_text(current_subtask, max(40, ceiling // 4))
            elif len(goal) > ceiling * 4 or len(goal.split()) > 40:
                goal = _shrink_text(goal, max(40, ceiling // 4))
            elif tool_results and len(tool_results[-1].truncated_output) > 80:
                last = tool_results[-1]
                tool_results[-1] = last.model_copy(
                    update={
                        "truncated_output": _shrink_text(
                            last.truncated_output, max(20, ceiling // 6)
                        )
                    }
                )
            elif tool_results:
                tool_results = tool_results[:-1]
            elif retrieved:
                retrieved = retrieved[:-1]
            elif constraints:
                longest = max(constraints, key=len)
                idx = constraints.index(longest)
                constraints[idx] = _shrink_text(longest, 20)
            elif len(current_subtask) > 60:
                current_subtask = _shrink_text(current_subtask, 15)
            elif len(goal) > 60:
                goal = _shrink_text(goal, 15)
            else:
                break

            wm = wm.model_copy(
                update={
                    "original_goal": goal,
                    "hard_constraints": constraints,
                    "current_subtask": current_subtask,
                    "retrieved_items": retrieved,
                    "tool_results": tool_results,
                    "recent_turn_recap": recent_turn_recap,
                }
            )

        if wm.token_count() > ceiling:
            wm = wm.model_copy(
                update={
                    "original_goal": _shrink_text(wm.original_goal, max(12, ceiling // 5)),
                    "current_subtask": _shrink_text(
                        wm.current_subtask, max(12, ceiling // 3)
                    ),
                    "hard_constraints": [
                        _shrink_text(c, 8) for c in wm.hard_constraints[:2]
                    ],
                    "retrieved_items": [],
                    "tool_results": tool_results[:1],
                    "recent_turn_recap": recent_turn_recap[:2],
                    "skill_card": (
                        _cap_tokens(wm.skill_card, 8) if wm.skill_card else None
                    ),
                    "last_error": (
                        _cap_tokens(wm.last_error, 8) if wm.last_error else None
                    ),
                }
            )

        if wm.token_count() > ceiling:
            raise WorkingMemoryBudgetError(
                f"Working memory {wm.token_count()} tokens exceeds "
                f"ceiling {ceiling} after truncation"
            )
        return wm

    def build(
        self,
        session_id: str,
        agent_role: str,
        current_subtask: str,
        subtask_id: str,
        last_error: str | None = None,
        retry_count: int = 0,
        *,
        interactive_turn_floor: int | None = None,
    ) -> WorkingMemory:
        """Assemble working memory; truncate if over profile token ceiling."""
        goal, constraints = self._memory.subtasks.get_session_anchor(session_id)
        if not goal:
            task = self._memory.subtasks.get(subtask_id)
            if task and task.original_goal:
                goal = task.original_goal
                constraints = list(task.hard_constraints)

        retrieved: list[str] = []
        tool_results: list[ToolResultEntry] = []
        recent_turn_recap: list[str] = []
        skill_card: str | None = None
        if interactive_turn_floor is not None:
            from framework.memory.tool_results import recent_turn_recap as build_recap

            tool_results = self._memory.tool_results.list_for_turn(
                session_id, interactive_turn_floor
            )
            recent_turn_recap = build_recap(
                self._memory,
                session_id,
                decision_floor=interactive_turn_floor,
            )
            if tool_results:
                logger.debug(
                    "[WM] tool_results_in_prompt session=%s count=%d floor=%d",
                    session_id,
                    len(tool_results),
                    interactive_turn_floor,
                )
        if self._enable_memory:
            index = self._memory.retrieval.list_items()
            top_items = retrieve_top_k(index, current_subtask, k=3)
            retrieved = [item.text_summary for item in top_items]

            skill_raw = select_skill_card(
                agent_role=agent_role,
                last_error=last_error,
                current_subtask=current_subtask,
            )
            skill_card = (
                _cap_tokens(skill_raw, self._profile.skill_budget_tokens)
                if skill_raw
                else None
            )

        wm = WorkingMemory(
            original_goal=goal,
            hard_constraints=constraints,
            agent_role=agent_role,
            agent_scope=_AGENT_SCOPES.get(agent_role, agent_role),
            current_subtask=current_subtask,
            subtask_id=subtask_id,
            retrieved_items=retrieved,
            tool_results=tool_results,
            recent_turn_recap=recent_turn_recap,
            last_error=last_error,
            retry_count=retry_count,
            skill_card=skill_card,
        )
        return self._fit_to_budget(wm)

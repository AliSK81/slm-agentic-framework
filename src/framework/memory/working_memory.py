"""Working Memory builder — assembles L1 context from L2 stores."""

from __future__ import annotations

import logging

from framework.memory.retrieval import _load_retrieval_config, _cap_tokens, estimate_tokens, retrieve_top_k
from framework.memory.stores import MemoryStores, ToolResultEntry, WorkingMemory
from framework.slm.client import ModelProfile
from framework.slm.skills import select_skill_card

logger = logging.getLogger(__name__)


def _cap_retrieved_items(summaries: list[str], max_tokens: int) -> list[str]:
    """Cap total retrieved text to ``max_tokens`` using the shared estimator."""
    if max_tokens <= 0:
        return []
    total = 0
    capped: list[str] = []
    for text in summaries:
        item_tokens = estimate_tokens(text)
        remaining = max_tokens - total
        if remaining <= 0:
            break
        if item_tokens <= remaining:
            capped.append(text)
            total += item_tokens
        else:
            capped.append(_cap_tokens(text, remaining))
            break
    return capped


def _shrink_text(text: str, max_tokens: int) -> str:
    """Cap text to ``max_tokens`` using the shared token estimator."""
    return _cap_tokens(text, max_tokens)


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

    def _assemble(
        self,
        *,
        goal: str,
        constraints: list[str],
        current_subtask: str,
        tool_results: list[ToolResultEntry],
        retrieved: list[str],
        recent_turn_recap: list[str],
        skill_card: str | None,
        last_error: str | None,
        wm: WorkingMemory,
    ) -> WorkingMemory:
        return wm.model_copy(
            update={
                "original_goal": goal,
                "hard_constraints": constraints,
                "current_subtask": current_subtask,
                "retrieved_items": retrieved,
                "tool_results": tool_results,
                "recent_turn_recap": recent_turn_recap,
                "skill_card": skill_card,
                "last_error": last_error,
            }
        )

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
        skill_card = wm.skill_card
        last_error = wm.last_error

        for _ in range(32):
            wm = self._assemble(
                goal=goal,
                constraints=constraints,
                current_subtask=current_subtask,
                tool_results=tool_results,
                retrieved=retrieved,
                recent_turn_recap=recent_turn_recap,
                skill_card=skill_card,
                last_error=last_error,
                wm=wm,
            )
            if wm.token_count() <= ceiling:
                return wm

            dropped: str | None = None
            if retrieved:
                retrieved.pop()
                dropped = "retrieved_items"
            elif skill_card:
                skill_card = None
                dropped = "skill_card"
            elif recent_turn_recap:
                recent_turn_recap.pop()
                dropped = "recent_turn_recap"
            elif tool_results and estimate_tokens(tool_results[-1].truncated_output) > max(
                20, ceiling // 6
            ):
                last = tool_results[-1]
                tool_results[-1] = last.model_copy(
                    update={
                        "truncated_output": _shrink_text(
                            last.truncated_output, max(20, ceiling // 6)
                        )
                    }
                )
                dropped = "tool_results.truncated_output"
            elif tool_results:
                tool_results.pop()
                dropped = "tool_results"
            elif estimate_tokens(current_subtask) > max(40, ceiling // 3):
                current_subtask = _shrink_text(current_subtask, max(40, ceiling // 4))
                dropped = "current_subtask"
            elif constraints and max(estimate_tokens(c) for c in constraints) > max(
                8, ceiling // 6
            ):
                constraints = [_shrink_text(c, max(8, ceiling // 8)) for c in constraints]
                dropped = "constraints"
            elif estimate_tokens(goal) > max(40, ceiling // 3):
                goal = _shrink_text(goal, max(40, ceiling // 4))
                dropped = "goal"
            else:
                break

            if dropped is not None:
                logger.debug(
                    "WM truncation adjusted field=%s tokens=%s ceiling=%s",
                    dropped,
                    wm.token_count(),
                    ceiling,
                )

        wm = self._assemble(
            goal=goal,
            constraints=constraints,
            current_subtask=current_subtask,
            tool_results=tool_results,
            retrieved=retrieved,
            recent_turn_recap=recent_turn_recap,
            skill_card=skill_card,
            last_error=last_error,
            wm=wm,
        )
        if wm.token_count() > ceiling:
            wm = wm.model_copy(
                update={
                    "retrieved_items": [],
                    "skill_card": None,
                    "recent_turn_recap": recent_turn_recap[:2],
                    "tool_results": tool_results[:1],
                    "current_subtask": _shrink_text(
                        current_subtask, max(12, ceiling // 3)
                    ),
                    "hard_constraints": [
                        _shrink_text(c, 8) for c in constraints[:2]
                    ],
                    "original_goal": _shrink_text(goal, max(12, ceiling // 5)),
                    "last_error": (
                        _cap_tokens(last_error, 8) if last_error else None
                    ),
                }
            )
            logger.debug(
                "WM truncation fallback applied tokens=%s ceiling=%s",
                wm.token_count(),
                ceiling,
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
            top_k = self._profile.retrieval_top_k or _load_retrieval_config()["top_k"]
            top_items = retrieve_top_k(index, current_subtask, k=top_k)
            retrieved_budget = max(1, self._profile.max_working_memory_tokens // 4)
            retrieved = _cap_retrieved_items(
                [item.text_summary for item in top_items],
                retrieved_budget,
            )

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

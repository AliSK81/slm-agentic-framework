"""Working Memory builder — assembles L1 context from L2 stores."""

from __future__ import annotations

from framework.memory.retrieval import _cap_tokens, retrieve_top_k
from framework.memory.stores import MemoryStores, WorkingMemory
from framework.slm.client import ModelProfile
from framework.slm.skills import select_skill_card

_AGENT_SCOPES = {
    "planner": "Decompose programming tasks into ordered sub-tasks. Do not write code or invoke tools.",
    "executor": "Implement the current sub-task using bounded tools. Do not change session goal or constraints.",
}


class WorkingMemoryBudgetError(ValueError):
    """Raised when assembled working memory exceeds the model token ceiling."""


class WorkingMemoryBuilder:
    """Builds L1 WorkingMemory from L2 stores and model profile."""

    def __init__(self, memory: MemoryStores, profile: ModelProfile) -> None:
        self._memory = memory
        self._profile = profile

    def build(
        self,
        session_id: str,
        agent_role: str,
        current_subtask: str,
        subtask_id: str,
        last_error: str | None = None,
        retry_count: int = 0,
    ) -> WorkingMemory:
        """Assemble working memory; raise if over profile token ceiling."""
        goal, constraints = self._memory.subtasks.get_session_anchor(session_id)
        if not goal:
            task = self._memory.subtasks.get(subtask_id)
            if task and task.original_goal:
                goal = task.original_goal
                constraints = list(task.hard_constraints)

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
            last_error=last_error,
            retry_count=retry_count,
            skill_card=skill_card,
        )

        if wm.token_count() > self._profile.max_working_memory_tokens:
            raise WorkingMemoryBudgetError(
                f"Working memory {wm.token_count()} tokens exceeds "
                f"ceiling {self._profile.max_working_memory_tokens}"
            )
        return wm

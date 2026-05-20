"""Planner agent unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.control.cycle import DecisionCycle
from framework.control.models import ErrorControlBundle
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import MemoryStores, SubTask
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.orchestration.planner import PlannerAgent
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
    """Queue-based SLM stub for planner tests."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.profile = ModelProfile(
            model_id="mock",
            context_limit=4096,
            effective_context=4096,
            max_working_memory_tokens=650,
            tool_output_caps={},
            skill_budget_tokens=120,
            timeout_by_role={"planner": 60, "executor": 75},
        )

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        _ = messages, role, json_mode
        if not self._responses:
            return SLMResponse(error="empty_queue", model="mock")
        content = self._responses.pop(0)
        return SLMResponse(content=content, model="mock", tokens_used=1, elapsed_ms=1)


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "planner.db"))


@pytest.fixture
def session_id(memory: MemoryStores) -> str:
    sid = "sess-planner"
    memory.subtasks.register(
        SubTask(
            task_id=f"root:{sid}",
            parent_session_id=sid,
            description="root",
            status="open",
            owner="planner",
            original_goal="Solve HumanEval/2",
            hard_constraints=[],
        )
    )
    return sid


def _planner(slm: MockSLMClient, memory: MemoryStores) -> PlannerAgent:
    builder = WorkingMemoryBuilder(memory, slm.profile)
    cycle = DecisionCycle(
        slm,
        memory,
        builder,
        ErrorControlBundle(),
        slm.profile,
        max_steps=20,
    )
    return PlannerAgent(cycle, memory)


def test_plan_node_coerces_numeric_task_id_from_slm(
    memory: MemoryStores,
    session_id: str,
) -> None:
    """When SLM returns task_id as int, SubTask registration still succeeds."""
    plan_json = json.dumps(
        {
            "kind": "plan_step",
            "rationale": "One step.",
            "payload": {
                "subtasks": [
                    {
                        "task_id": 1,
                        "description": "Implement truncate_number",
                        "owner": "executor",
                        "depends_on": [2],
                    }
                ]
            },
            "references": [],
        }
    )
    planner = _planner(MockSLMClient([plan_json]), memory)
    planner.plan_node(
        {
            "session_id": session_id,
            "goal": "Solve HumanEval/2",
            "current_state": "PLAN",
            "step_count": 0,
        }
    )
    tasks = [
        t
        for t in memory.backend.query("subtasks", {"parent_session_id": session_id})
        if not str(t["task_id"]).startswith("root:")
    ]
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "1"
    assert tasks[0]["depends_on"] == ["2"]

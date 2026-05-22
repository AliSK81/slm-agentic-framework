"""Output-token efficiency unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.control.cycle import DecisionCycle, _json_format_block
from framework.control.models import ErrorControlBundle
from framework.memory.stores import MemoryStores, WorkingMemory, Issue
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
    """Minimal SLM stub for cycle prompt construction tests."""

    profile = ModelProfile(
        model_id="mock",
        context_limit=4096,
        effective_context=4096,
        max_working_memory_tokens=480,
        tool_output_caps={},
        skill_budget_tokens=90,
        timeout_by_role={"planner": 60, "executor": 75},
    )

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        _ = messages, role, json_mode
        return SLMResponse(error="unused", model="mock")


def test_json_format_compact_omits_example_block() -> None:
    """Compact format block has required keys but no Example line."""
    full = _json_format_block("executor", include_example=True)
    compact = _json_format_block("executor", include_example=False)
    assert "Example:" in full
    assert "Example:" not in compact
    assert "kind" in compact


def test_corrective_retry_after_self_check_uses_compact_format(
    memory: MemoryStores,
) -> None:
    """Self-check corrective prompts (retry > 0) omit the full JSON example."""
    profile = ModelProfile(
        model_id="mock",
        context_limit=4096,
        effective_context=4096,
        max_working_memory_tokens=480,
        tool_output_caps={},
        skill_budget_tokens=90,
        timeout_by_role={"planner": 60, "executor": 75},
    )
    wm = WorkingMemory(
        original_goal="g",
        hard_constraints=[],
        agent_role="executor",
        agent_scope="executor scope",
        current_subtask="task",
        subtask_id="st-1",
    )
    cycle = DecisionCycle(
        MockSLMClient(),
        memory,
        WorkingMemoryBuilder(memory, profile),
        ErrorControlBundle(),
        profile,
    )
    messages = cycle._build_corrective_prompt(
        wm,
        [Issue(kind="schema_violation", detail="bad rationale")],
        2,
        "executor",
        include_example=False,
    )
    content = messages[0]["content"]
    assert "CORRECTION RETRY 2" in content
    assert "Example:" not in content


def test_schema_failure_corrective_includes_example_block(
    memory: MemoryStores,
) -> None:
    """Schema-failure retries keep the full example block."""
    profile = ModelProfile(
        model_id="mock",
        context_limit=4096,
        effective_context=4096,
        max_working_memory_tokens=480,
        tool_output_caps={},
        skill_budget_tokens=90,
        timeout_by_role={"planner": 60, "executor": 75},
    )
    wm = WorkingMemory(
        original_goal="g",
        hard_constraints=[],
        agent_role="executor",
        agent_scope="executor scope",
        current_subtask="task",
        subtask_id="st-1",
    )
    cycle = DecisionCycle(
        MockSLMClient(),
        memory,
        WorkingMemoryBuilder(memory, profile),
        ErrorControlBundle(),
        profile,
    )
    messages = cycle._build_corrective_prompt(
        wm,
        [Issue(kind="schema_violation", detail="unparseable")],
        1,
        "executor",
        include_example=True,
    )
    assert "Example:" in messages[0]["content"]


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    from framework.memory.backend import SQLiteBackend

    return MemoryStores(SQLiteBackend(tmp_path / "wm.db"))

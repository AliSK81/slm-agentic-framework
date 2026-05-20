"""Output-token efficiency unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aviona.profiles import DAILY_DRIVER_PROFILE, apply_daily_driver_profiles
from aviona.render import STATUS_MAX_WIDTH, render_status
from framework.control.cycle import DecisionCycle, _json_format_block
from framework.control.models import ErrorControlBundle
from framework.memory.stores import MemoryStores, WorkingMemory, Issue
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.orchestration.session import SessionOutcome
from framework.slm.config import load_profile
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


def test_render_status_is_single_line_within_width() -> None:
    """render_status returns one line capped at STATUS_MAX_WIDTH."""
    outcome = SessionOutcome(
        session_id="s",
        outcome="solved",
        test_passed=True,
        step_count=3,
        tokens_total=1200,
    )
    line = render_status(outcome, edited_path="solution.py")
    assert "\n" not in line
    assert len(line) <= STATUS_MAX_WIDTH


def test_aviona_daily_profile_has_lower_wm_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Daily-driver profile lowers working-memory and skill budgets vs default."""
    monkeypatch.delenv("PLANNER_PROFILE", raising=False)
    monkeypatch.delenv("EXECUTOR_PROFILE", raising=False)
    apply_daily_driver_profiles()
    daily = load_profile(DAILY_DRIVER_PROFILE)
    thesis = load_profile("deepseek-v4-flash")
    assert daily.max_working_memory_tokens < thesis.max_working_memory_tokens
    assert daily.skill_budget_tokens < thesis.skill_budget_tokens


def test_wm_builder_uses_daily_driver_ceiling(
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WorkingMemoryBuilder truncates to aviona-daily max_working_memory_tokens."""
    from framework.memory.stores import SubTask

    session_id = "sess-wm"
    memory.subtasks.register(
        SubTask(
            task_id=f"root:{session_id}",
            parent_session_id=session_id,
            description="root",
            status="open",
            owner="planner",
            original_goal="Build X",
            hard_constraints=["c"] * 50,
        )
    )
    profile = load_profile(DAILY_DRIVER_PROFILE)
    builder = WorkingMemoryBuilder(memory, profile)
    wm = builder.build(
        session_id=session_id,
        agent_role="planner",
        current_subtask="plan",
        subtask_id=f"root:{session_id}",
    )
    prompt = wm.to_prompt_prefix()
    assert len(prompt.split()) <= profile.max_working_memory_tokens + 50

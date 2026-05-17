"""Decision Cycle integration tests with mocked SLM."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework.control.cycle import DecisionCycle
from framework.control.models import ErrorControlBundle
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import DecisionEntry, MemoryStores, SubTask
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
    """Queue-based SLM stub for cycle tests."""

    def __init__(
        self,
        responses: list[str],
        profile: ModelProfile | None = None,
    ) -> None:
        self._responses = list(responses)
        self.profile = profile or ModelProfile(
            openrouter_id="mock",
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


def _valid_executor_json() -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "payload": {"tool": "pytest"},
            "rationale": "Run tests for the subtask.",
            "references": [],
        }
    )


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "cycle.db"))


@pytest.fixture
def session_setup(memory: MemoryStores) -> str:
    session_id = "sess-cycle"
    memory.subtasks.register(
        SubTask(
            task_id=f"root:{session_id}",
            parent_session_id=session_id,
            description="root",
            status="open",
            owner="planner",
            original_goal="Build feature X",
            hard_constraints=["No external network"],
        )
    )
    return session_id


def _cycle(
    slm: MockSLMClient,
    memory: MemoryStores,
    *,
    max_steps: int = 20,
) -> DecisionCycle:
    profile = slm.profile
    builder = WorkingMemoryBuilder(memory, profile)
    return DecisionCycle(
        slm,
        memory,
        builder,
        ErrorControlBundle(),
        profile,
        max_steps=max_steps,
    )


def test_cycle_completes_on_valid_proposal(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """Mocked SLM returns valid JSON → cycle completes, decision recorded."""
    slm = MockSLMClient([_valid_executor_json()])
    cycle = _cycle(slm, memory)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: {"ok": True},
    )
    assert not result.exhausted
    assert result.decision is not None
    assert result.outcome == {"ok": True}


def test_cycle_retries_on_schema_fail(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """Invalid JSON then valid → success after retry."""
    slm = MockSLMClient(["not-json", _valid_executor_json()])
    cycle = _cycle(slm, memory)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: "acted",
        max_retries=3,
    )
    assert not result.exhausted
    assert result.retry_count == 1
    assert result.decision is not None


def test_cycle_marks_exhausted_after_max_retries(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """SLM always invalid → exhausted after max_retries."""
    slm = MockSLMClient(["bad", "also-bad", "still-bad", "nope"])
    cycle = _cycle(slm, memory)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: None,
        max_retries=2,
    )
    assert result.exhausted


def test_cycle_records_decision_in_log(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """After successful cycle → DecisionLog has exactly 1 new entry."""
    slm = MockSLMClient([_valid_executor_json()])
    cycle = _cycle(slm, memory)
    before = len(memory.decisions.list_for_session(session_setup))
    cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: None,
    )
    after = len(memory.decisions.list_for_session(session_setup))
    assert after - before == 1


def test_cycle_records_self_check_result(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """DecisionEntry in log has self_check.verdict == 'pass'."""
    slm = MockSLMClient([_valid_executor_json()])
    cycle = _cycle(slm, memory)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: None,
    )
    assert result.decision is not None
    assert result.decision.self_check.verdict == "pass"
    logged = memory.decisions.get_last_n(session_setup, 1)[0]
    assert logged.self_check.verdict == "pass"


def test_budget_limiter_stops_cycle(
    memory: MemoryStores,
    session_setup: str,
) -> None:
    """max_steps=1, step_count=1 → budget_exceeded before calling SLM."""
    slm = MockSLMClient([_valid_executor_json()])
    cycle = _cycle(slm, memory, max_steps=1)
    result = cycle.run(
        session_setup,
        "executor",
        "run pytest",
        f"root:{session_setup}",
        action_fn=lambda d: None,
        step_count=1,
        max_steps=1,
    )
    assert result.budget_exceeded
    assert slm._responses  # SLM never called

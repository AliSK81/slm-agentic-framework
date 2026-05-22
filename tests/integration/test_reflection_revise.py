"""Integration tests for REVISE-time reflection (error_control-gated)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from framework.control.ablation import AblationSettings
from framework.control.cycle import DecisionCycle
from framework.control.models import ErrorControlBundle
from framework.control.workflow import STATE_EVALUATE, WorkflowState
from framework.memory.backend import SQLiteBackend
from framework.memory.reflection import write_reflection
from framework.memory.stores import MemoryStores, SubTask
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.orchestration.executor import ExecutorAgent
from framework.orchestration.messages import DispatchMessage, save_dispatch
from framework.orchestration.session import _run_revise_reflection
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
    """SLM stub that returns reflection text on non-JSON calls."""

    def __init__(self, reflection_text: str = "Use addition instead of subtraction.") -> None:
        self.reflection_text = reflection_text
        self.calls: list[tuple[str, bool]] = []
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
        self.calls.append((role, json_mode))
        if not json_mode:
            return SLMResponse(
                content=self.reflection_text,
                model="mock",
                tokens_used=3,
                elapsed_ms=1,
            )
        return SLMResponse(
            content=json.dumps(
                {
                    "kind": "code_edit",
                    "payload": {"file_path": "solution.py", "content": "def f():\n    pass\n"},
                    "rationale": "edit",
                    "references": [],
                }
            ),
            model="mock",
            tokens_used=1,
            elapsed_ms=1,
        )


@pytest.fixture
def mock_slm() -> MockSLMClient:
    return MockSLMClient()


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    store = MemoryStores(SQLiteBackend(tmp_path / "reflection.db"))
    store.subtasks.register(
        SubTask(
            task_id="st-main",
            parent_session_id="sess-reflect",
            description="fix multiply function",
            status="open",
            owner="executor",
        )
    )
    return store


def _revise_state(**overrides: Any) -> WorkflowState:
    state: WorkflowState = {
        "session_id": "sess-reflect",
        "goal": "Fix multiply",
        "hard_constraints": [],
        "current_state": STATE_EVALUATE,
        "active_subtask_id": "st-main",
        "step_count": 2,
        "retry_count": 1,
        "loop_count": 0,
        "max_steps": 10,
        "max_retries": 3,
        "last_evaluation": {"passed": False, "error_message": "assert 12 == -1"},
        "reflection_guidance": None,
    }
    state.update(overrides)
    return state


def test_reflection_called_on_revise_when_error_control_on(
    mock_slm: MockSLMClient,
    memory: MemoryStores,
) -> None:
    """error_control on → REVISE handler appends a reflection decision."""
    before = len(memory.decisions.list_for_session("sess-reflect"))
    state = _run_revise_reflection(
        _revise_state(),
        memory,
        "Fix multiply",
        mock_slm,
        AblationSettings(error_control=True),
    )

    assert state.get("reflection_guidance")
    assert len(memory.decisions.list_for_session("sess-reflect")) == before + 1
    assert any(call[1] is False for call in mock_slm.calls)


def test_reflection_not_called_when_error_control_off(
    mock_slm: MockSLMClient,
    memory: MemoryStores,
) -> None:
    """Configs without error_control do not call reflection on REVISE."""
    before = len(memory.decisions.list_for_session("sess-reflect"))
    state = _run_revise_reflection(
        _revise_state(),
        memory,
        "Fix multiply",
        mock_slm,
        AblationSettings(memory=False, control=True, error_control=False),
    )

    assert state.get("reflection_guidance") is None
    assert len(memory.decisions.list_for_session("sess-reflect")) == before
    assert mock_slm.calls == []


def test_reflection_skipped_when_profile_reflection_disabled(
    mock_slm: MockSLMClient,
    memory: MemoryStores,
) -> None:
    """error_control on but reflection_enabled false → no reflection decision."""
    mock_slm.profile = mock_slm.profile.model_copy(update={"reflection_enabled": False})
    before = len(memory.decisions.list_for_session("sess-reflect"))
    state = _run_revise_reflection(
        _revise_state(),
        memory,
        "Fix multiply",
        mock_slm,
        AblationSettings(error_control=True),
    )

    assert state.get("reflection_guidance") is None
    assert len(memory.decisions.list_for_session("sess-reflect")) == before
    assert mock_slm.calls == []


def test_reflection_capped_per_subtask(mock_slm: MockSLMClient, memory: MemoryStores) -> None:
    """Reflection entries stop at max_reflections_per_subtask from memory.yaml."""
    settings = AblationSettings(error_control=True)
    for _ in range(5):
        _run_revise_reflection(
            _revise_state(),
            memory,
            "Fix multiply",
            mock_slm,
            settings,
        )
    reflections = [
        entry
        for entry in memory.decisions.list_for_session("sess-reflect")
        if entry.kind == "reflection"
    ]
    assert len(reflections) == 3


def test_reflection_text_feeds_next_attempt_as_guidance(
    mock_slm: MockSLMClient,
    memory: MemoryStores,
    tmp_path: Path,
) -> None:
    """Executor cycle receives reflection text as last_error on retry."""
    guidance = "Replace subtraction with multiplication in multiply()."
    state = _run_revise_reflection(
        _revise_state(),
        memory,
        "Fix multiply",
        MockSLMClient(guidance),
        AblationSettings(error_control=True),
    )

    captured: dict[str, str | None] = {}

    def capture_run(*_args: object, **kwargs: object) -> Any:
        captured["last_error"] = kwargs.get("last_error")  # type: ignore[assignment]
        from framework.control.models import CycleResult

        return CycleResult(decision=None, exhausted=False)

    save_dispatch(
        memory.backend,
        DispatchMessage(
            session_id="sess-reflect",
            task_id="st-main",
            subtask_description="fix multiply function",
            step_budget=5,
        ),
    )
    cycle = DecisionCycle(
        mock_slm,
        memory,
        WorkingMemoryBuilder(memory, mock_slm.profile),
        ErrorControlBundle(),
        mock_slm.profile,
    )
    from framework.orchestration.messages import load_dispatch

    assert load_dispatch(memory.backend, "sess-reflect") is not None
    executor = ExecutorAgent(cycle, memory, tmp_path / "workspace")
    with patch.object(cycle, "run", side_effect=capture_run):
        executor.execute_node(state)

    assert captured["last_error"] == guidance


def test_reflection_recorded_as_decision_entry(
    mock_slm: MockSLMClient,
    memory: MemoryStores,
) -> None:
    """Reflection is stored as DecisionEntry(kind=reflection, importance via retrieval)."""
    text = write_reflection(
        mock_slm,
        "sess-reflect",
        3,
        "Fix multiply",
        "fix multiply function",
        2,
        "pytest failed",
        memory,
        subtask_id="st-main",
    )
    entry = memory.decisions.get_last_n("sess-reflect", 1)[0]
    assert text
    assert entry.kind == "reflection"
    assert entry.payload.get("text") == text
    assert entry.payload.get("linked_subtask") == "st-main"
    from framework.memory.stores import _importance_for_kind

    assert _importance_for_kind("reflection") == 1.0

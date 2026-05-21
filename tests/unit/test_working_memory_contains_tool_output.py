"""FI-2: typed tool-result channel in working memory."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path

from framework.memory.backend import SQLiteBackend
from framework.memory.stores import (
    DecisionEntry,
    MemoryStores,
    SelfCheckRecord,
    SubTask,
)
from framework.memory.tool_results import append_tool_result
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.orchestration.session import _run_interactive_executor_turn
from framework.slm.client import ModelProfile


def test_prompt_contains_truncated_read_file_in_tool_results(tmp_path: Path) -> None:
    """After read_file, the next WM prompt includes file body under [TOOL RESULTS]."""
    memory = MemoryStores(SQLiteBackend(tmp_path / "wm.db"))
    session_id = "sess-wm"
    turn_floor = 0
    body = "line one\nline two\nline three"
    append_tool_result(
        memory,
        session_id=session_id,
        turn_floor=turn_floor,
        tool="read_file",
        path="solution.py",
        output=body,
        ok=True,
    )
    memory.subtasks.register(
        SubTask(
            task_id="root:sess-wm",
            parent_session_id=session_id,
            description="root",
            status="open",
            owner="planner",
            original_goal="read solution.py",
            hard_constraints=[],
        )
    )
    profile = ModelProfile(
        model_id="mock",
        context_limit=4096,
        effective_context=4096,
        max_working_memory_tokens=2000,
        tool_output_caps={"read_file": 12000},
        skill_budget_tokens=120,
        timeout_by_role={"executor": 60},
    )
    builder = WorkingMemoryBuilder(memory, profile, enable_memory=False)
    wm = builder.build(
        session_id,
        "executor",
        "read solution.py",
        "st-main",
        interactive_turn_floor=turn_floor,
    )
    prefix = wm.to_prompt_prefix()
    assert "[TOOL RESULTS]" in prefix
    assert "line one" in prefix
    assert "solution.py" in prefix


def test_recent_turns_lists_edited_path(tmp_path: Path) -> None:
    """[RECENT TURNS] includes code_edit paths from the current turn."""
    memory = MemoryStores(SQLiteBackend(tmp_path / "rt.db"))
    session_id = "sess-rt"
    memory.decisions.append(
        DecisionEntry(
            session_id=session_id,
            decision_id="d-edit",
            step_index=0,
            by_agent="executor",
            kind="code_edit",
            payload={"file_path": "foo.txt", "turn_type": "edit"},
            rationale="create file",
            references=[],
            self_check=SelfCheckRecord(verdict="pass", issues=[]),
            timestamp=datetime.now(UTC),
        )
    )
    memory.subtasks.register(
        SubTask(
            task_id="root:sess-rt",
            parent_session_id=session_id,
            description="root",
            status="open",
            owner="planner",
            original_goal="create foo.txt",
            hard_constraints=[],
        )
    )
    profile = ModelProfile(
        model_id="mock",
        context_limit=4096,
        effective_context=4096,
        max_working_memory_tokens=2000,
        tool_output_caps={},
        skill_budget_tokens=120,
        timeout_by_role={"executor": 60},
    )
    wm = WorkingMemoryBuilder(memory, profile, enable_memory=False).build(
        session_id,
        "executor",
        "create foo.txt",
        "st-main",
        interactive_turn_floor=0,
    )
    prefix = wm.to_prompt_prefix()
    assert "[RECENT TURNS]" in prefix
    assert "edited: foo.txt" in prefix


def test_interactive_executor_turn_does_not_assign_reflection_guidance() -> None:
    """Interactive path uses cycle_last_error, not reflection_guidance injection."""
    source = inspect.getsource(_run_interactive_executor_turn)
    assert 'state["reflection_guidance"]' not in source
    assert "cycle_last_error" in source

"""Working memory builder and retrieval unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework.memory.backend import SQLiteBackend
from framework.memory.retrieval import keyword_overlap, retrieve_top_k, score
from framework.memory.stores import MemoryStores, RetrievalItem, SubTask, WorkingMemory
from framework.memory.working_memory import WorkingMemoryBuilder
from framework.slm.client import ModelProfile
from framework.slm.skills import load_skill_cards, select_skill_card


def _profile(*, max_wm: int = 650, skill_budget: int = 120) -> ModelProfile:
    return ModelProfile(
        model_id="qwen/qwen-2.5-coder-7b-instruct",
        context_limit=32768,
        effective_context=12000,
        max_working_memory_tokens=max_wm,
        tool_output_caps={},
        skill_budget_tokens=skill_budget,
        timeout_by_role={"planner": 60, "executor": 75},
    )


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "wm.db"))


def _register_session(
    memory: MemoryStores,
    session_id: str,
    goal: str,
    constraints: list[str],
) -> None:
    memory.subtasks.register(
        SubTask(
            task_id=f"root:{session_id}",
            parent_session_id=session_id,
            description="Session root",
            status="open",
            owner="planner",
            original_goal=goal,
            hard_constraints=constraints,
        )
    )


def test_working_memory_stays_under_token_ceiling(memory: MemoryStores) -> None:
    """Builder truncates assembled WM to fit profile.max_working_memory_tokens."""
    _register_session(
        memory,
        "sess-budget",
        goal="x" * 5000,
        constraints=["y" * 2000],
    )
    builder = WorkingMemoryBuilder(memory, _profile(max_wm=120))
    wm = builder.build(
        session_id="sess-budget",
        agent_role="executor",
        current_subtask="do work " * 400,
        subtask_id="root:sess-budget",
    )
    assert wm.token_count() <= 120


def test_anchor_always_present(memory: MemoryStores) -> None:
    """goal and hard_constraints always appear in to_prompt_prefix() output."""
    _register_session(
        memory,
        "sess-anchor",
        goal="Implement add(a,b)",
        constraints=["Must return a+b"],
    )
    wm = WorkingMemoryBuilder(memory, _profile()).build(
        session_id="sess-anchor",
        agent_role="planner",
        current_subtask="Plan decomposition",
        subtask_id="root:sess-anchor",
    )
    prefix = wm.to_prompt_prefix()
    assert "[GOAL]: Implement add(a,b)" in prefix
    assert "Must return a+b" in prefix


def test_retrieved_items_capped_at_3(memory: MemoryStores) -> None:
    """Even if 10 items in index, WM.retrieved_items has at most 3."""
    _register_session(memory, "sess-k", goal="g", constraints=[])
    now = datetime.now(UTC)
    for i in range(10):
        memory.retrieval.append(
            RetrievalItem(
                item_ref=f"i-{i}",
                text_summary=f"shared keyword item number {i}",
                importance=0.5,
                written_at=now,
                last_accessed=now,
            )
        )
    wm = WorkingMemoryBuilder(memory, _profile()).build(
        session_id="sess-k",
        agent_role="executor",
        current_subtask="keyword shared task",
        subtask_id="root:sess-k",
    )
    assert len(wm.retrieved_items) <= 3


def test_retrieved_item_text_capped_at_150_tokens(memory: MemoryStores) -> None:
    """Items with long text are truncated to 150 tokens each."""
    _register_session(memory, "sess-cap", goal="g", constraints=[])
    long_text = " ".join(["token"] * 300)
    now = datetime.now(UTC)
    memory.retrieval.append(
        RetrievalItem(
            item_ref="long-1",
            text_summary=long_text,
            importance=1.0,
            written_at=now,
            last_accessed=now,
        )
    )
    wm = WorkingMemoryBuilder(memory, _profile()).build(
        session_id="sess-cap",
        agent_role="executor",
        current_subtask="token token uniquecapquery",
        subtask_id="root:sess-cap",
    )
    assert len(wm.retrieved_items) == 1
    assert len(wm.retrieved_items[0].split()) <= 150


def test_skill_card_selected_by_error_signal() -> None:
    """last_error containing 'SyntaxError' → executor_compile_error card selected."""
    card = select_skill_card(
        agent_role="executor",
        last_error="SyntaxError: invalid syntax at line 4",
        current_subtask="unrelated text",
    )
    assert card is not None
    compile_cards = [c for c in load_skill_cards() if c.name == "executor_compile_error"]
    assert compile_cards
    assert card == compile_cards[0].content


def test_skill_card_none_when_no_match() -> None:
    """No matching card → skill_card is None, no crash."""
    card = select_skill_card(
        agent_role="executor",
        last_error=None,
        current_subtask="zzzz no triggers here zzzz",
    )
    assert card is None

    wm = WorkingMemory(
        original_goal="g",
        hard_constraints=[],
        agent_role="executor",
        agent_scope="scope",
        current_subtask="zzzz",
        subtask_id="t-1",
        skill_card=card,
    )
    assert wm.skill_card is None


def test_retrieve_empty_when_no_relevance() -> None:
    """Zero keyword overlap returns empty top-k instead of noise."""
    now = datetime.now(UTC)
    index = [
        RetrievalItem(
            item_ref=f"noise-{i}",
            text_summary="unrelated database migration kubernetes",
            importance=1.0,
            written_at=now,
            last_accessed=now,
        )
        for i in range(5)
    ]
    assert retrieve_top_k(index, "implement binary search tree", k=3) == []


def test_zero_relevance_items_do_not_rank_from_importance() -> None:
    """Importance alone must not produce a non-zero score when overlap is zero."""
    now = datetime.now(UTC)
    item = RetrievalItem(
        item_ref="noise",
        text_summary="kubernetes pod scheduling unrelated",
        importance=1.0,
        written_at=now,
        last_accessed=now,
    )
    assert keyword_overlap(item, "fix multiply function") == 0.0
    assert score(item, "fix multiply function", now) == 0.0


def test_reflection_decision_not_indexed_for_retrieval(memory: MemoryStores) -> None:
    """Reflection and quality_failure stay in decision log only, not retrieval index."""
    from framework.memory.stores import DecisionEntry, SelfCheckRecord

    before = memory.retrieval.count()
    for kind in ("reflection", "quality_failure"):
        memory.decisions.append(
            DecisionEntry(
                session_id="sess-skip",
                decision_id=f"d-{kind}",
                step_index=0,
                by_agent="executor",
                kind=kind,
                payload={"text": "meta"},
                rationale=f"{kind} rationale",
                references=[],
                self_check=SelfCheckRecord(verdict="pass", issues=[]),
                timestamp=datetime.now(UTC),
            )
        )
    assert memory.retrieval.count() == before


def test_retrieved_total_capped_at_quarter_wm_ceiling(memory: MemoryStores) -> None:
    """Total retrieved text in WM is capped at ~25% of profile max_working_memory_tokens."""
    _register_session(memory, "sess-quota", goal="g", constraints=[])
    now = datetime.now(UTC)
    for i in range(3):
        memory.retrieval.append(
            RetrievalItem(
                item_ref=f"chunk-{i}",
                text_summary=" ".join(["sharedkeyword"] * 120),
                importance=0.5,
                written_at=now,
                last_accessed=now,
            )
        )
    ceiling = 400
    wm = WorkingMemoryBuilder(memory, _profile(max_wm=ceiling)).build(
        session_id="sess-quota",
        agent_role="executor",
        current_subtask="sharedkeyword task",
        subtask_id="root:sess-quota",
    )
    total_words = sum(len(item.split()) for item in wm.retrieved_items)
    assert total_words <= ceiling // 4

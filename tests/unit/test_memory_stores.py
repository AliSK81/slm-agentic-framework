"""Memory store unit tests — tmp_path SQLite, no external services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from framework.memory.backend import SQLiteBackend
from framework.memory.retrieval import keyword_overlap, retrieve_top_k, score
from framework.memory.stores import (
    DecisionEntry,
    DecisionLog,
    InteractionResult,
    MemoryStores,
    RetrievalItem,
    SelfCheckRecord,
    StateEntry,
    SubTask,
)


def _self_check() -> SelfCheckRecord:
    return SelfCheckRecord(verdict="pass", issues=[])


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "mem.db"))


def test_state_store_write_creates_new_snapshot(memory: MemoryStores) -> None:
    """Writing twice creates two entries with step_index 0 and 1."""
    now = datetime.now(UTC)
    base = dict(
        session_id="sess-1",
        artifact_hash="abc",
        tests_status={"passed": 1, "failed": 0, "errors": 0},
        open_subtasks=[],
        timestamp=now,
    )
    first = memory.state.write(StateEntry(step_index=99, **base))
    second = memory.state.write(StateEntry(step_index=99, **base))
    assert first.step_index == 0
    assert second.step_index == 1
    snapshots = memory.state.list_for_session("sess-1")
    assert len(snapshots) == 2


def test_decision_log_is_append_only() -> None:
    """No update or delete method exists on DecisionLog."""
    assert not hasattr(DecisionLog, "update")
    assert not hasattr(DecisionLog, "delete")


def test_decision_log_get_last_n(memory: MemoryStores) -> None:
    """get_last_n(session_id, 3) returns the 3 most recent entries."""
    now = datetime.now(UTC)
    for i in range(5):
        memory.decisions.append(
            DecisionEntry(
                session_id="sess-2",
                decision_id=f"d-{i}",
                step_index=i,
                by_agent="planner",
                kind="plan_step",
                payload={},
                rationale=f"step {i}",
                references=[],
                self_check=_self_check(),
                timestamp=now + timedelta(seconds=i),
            )
        )
    last_three = memory.decisions.get_last_n("sess-2", 3)
    assert len(last_three) == 3
    assert [e.decision_id for e in last_three] == ["d-4", "d-3", "d-2"]


def test_subtask_status_transition(memory: MemoryStores) -> None:
    """set_status('open' → 'in_progress') succeeds; 'done' → 'open' raises."""
    memory.subtasks.register(
        SubTask(
            task_id="t-1",
            parent_session_id="sess-3",
            description="fix bug",
            status="open",
            owner="executor",
            depends_on=[],
            result_ref=None,
            attempt_count=0,
        )
    )
    updated = memory.subtasks.set_status("t-1", "in_progress")
    assert updated.status == "in_progress"
    memory.subtasks.set_status("t-1", "done")
    with pytest.raises(ValueError, match="Invalid status transition"):
        memory.subtasks.set_status("t-1", "open")


def test_result_store_append(memory: MemoryStores) -> None:
    """Two results for same subtask are both stored and retrievable."""
    now = datetime.now(UTC)
    for idx in range(2):
        memory.results.append(
            InteractionResult(
                result_id=f"r-{idx}",
                kind="pytest_run",
                passed=idx == 1,
                failed_tests=[],
                error_message=None,
                stdout="",
                stderr="",
                exit_code=0 if idx == 1 else 1,
                linked_subtask="t-9",
                timestamp=now,
            )
        )
    rows = memory.results.list_for_subtask("t-9")
    assert len(rows) == 2
    assert {r.result_id for r in rows} == {"r-0", "r-1"}


def test_retrieval_item_appended_on_every_write(memory: MemoryStores) -> None:
    """After writing to DecisionLog, retrieval index has one new item."""
    before = memory.retrieval.count()
    memory.decisions.append(
        DecisionEntry(
            session_id="sess-4",
            decision_id="d-100",
            step_index=0,
            by_agent="executor",
            kind="tool_call",
            payload={"tool": "pytest"},
            rationale="run tests",
            references=[],
            self_check=_self_check(),
            timestamp=datetime.now(UTC),
        )
    )
    assert memory.retrieval.count() == before + 1


def test_retrieval_scoring_ranks_recent_higher() -> None:
    """Two items same importance/relevance; newer one scores higher."""
    now = datetime.now(UTC)
    query = "same summary text"
    older = RetrievalItem(
        item_ref="a",
        text_summary="same summary text",
        importance=0.5,
        written_at=now - timedelta(hours=10),
        last_accessed=now - timedelta(hours=10),
    )
    newer = RetrievalItem(
        item_ref="b",
        text_summary="same summary text",
        importance=0.5,
        written_at=now,
        last_accessed=now,
    )
    assert score(newer, query, now) > score(older, query, now)


def test_retrieval_scoring_ranks_important_higher() -> None:
    """Two items same recency/relevance; importance=1.0 scores higher than 0.5."""
    now = datetime.now(UTC)
    query = "identical"
    low = RetrievalItem(
        item_ref="a",
        text_summary="identical",
        importance=0.5,
        written_at=now,
        last_accessed=now,
    )
    high = RetrievalItem(
        item_ref="b",
        text_summary="identical",
        importance=1.0,
        written_at=now,
        last_accessed=now,
    )
    assert score(high, query, now) > score(low, query, now)


def test_retrieve_top_k_returns_k_items() -> None:
    """10 items in index, k=3 → 3 items returned when query overlaps."""
    now = datetime.now(UTC)
    index = [
        RetrievalItem(
            item_ref=f"i-{i}",
            text_summary=f"item {i}",
            importance=0.5,
            written_at=now,
            last_accessed=now,
        )
        for i in range(10)
    ]
    top = retrieve_top_k(index, "item", k=3)
    assert len(top) == 3


def test_retrieve_empty_when_no_relevance() -> None:
    """Unrelated index rows with zero overlap return no items."""
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
    top = retrieve_top_k(index, "implement binary search tree", k=3)
    assert top == []


def test_zero_relevance_items_do_not_rank_from_importance() -> None:
    """High-importance rows with zero overlap score below min relevance gate."""
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


def test_sqlite_backend_persists_across_instances(tmp_path: Path) -> None:
    """Write with instance A, read with fresh instance B → data present."""
    db = tmp_path / "persist.db"
    stores_a = MemoryStores(SQLiteBackend(db))
    stores_a.subtasks.register(
        SubTask(
            task_id="persist-1",
            parent_session_id="sess-p",
            description="persist me",
            status="open",
            owner="planner",
            depends_on=[],
            result_ref=None,
            attempt_count=0,
        )
    )
    stores_b = MemoryStores(SQLiteBackend(db))
    loaded = stores_b.subtasks.get("persist-1")
    assert loaded is not None
    assert loaded.description == "persist me"

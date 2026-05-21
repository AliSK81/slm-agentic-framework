"""Typed L2 memory stores and retrieval index."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from framework.memory.backend import MemoryBackend, SQLiteBackend

STORE_STATE = "state"
STORE_DECISIONS = "decisions"
STORE_SUBTASKS = "subtasks"
STORE_RESULTS = "results"
STORE_TOOL_RESULTS = "tool_results"
STORE_RETRIEVAL = "retrieval_index"

_VALID_SUBTASK_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("open", "in_progress"),
        ("open", "abandoned"),
        ("in_progress", "done"),
        ("in_progress", "abandoned"),
    }
)


class Issue(BaseModel):
    """Single self-check issue."""

    kind: Literal[
        "schema_violation",
        "contradiction",
        "scope_violation",
        "empty",
        "loop",
        "turn_type_required",
        "must_terminate_after_tool",
        "repeat_tool",
        "must_terminate_after_edit",
    ]
    detail: str


class SelfCheckRecord(BaseModel):
    """Outcome of SELF_CHECK for a decision."""

    verdict: Literal["pass", "fail", "exhausted"]
    issues: list[Issue] = Field(default_factory=list)


class StateEntry(BaseModel):
    """Versioned session state snapshot."""

    session_id: str
    step_index: int
    artifact_hash: str
    tests_status: dict[str, int]
    open_subtasks: list[str]
    timestamp: datetime


class DecisionEntry(BaseModel):
    """Append-only decision log record."""

    session_id: str
    decision_id: str
    step_index: int
    by_agent: Literal["planner", "executor"]
    kind: Literal[
        "plan_step",
        "code_edit",
        "tool_call",
        "handoff",
        "terminate",
        "reflection",
        "quality_failure",
    ]
    payload: dict[str, Any]
    rationale: str
    references: list[str] = Field(default_factory=list)
    self_check: SelfCheckRecord
    timestamp: datetime


class SubTask(BaseModel):
    """Mutable subtask registry entry."""

    task_id: str
    parent_session_id: str
    description: str
    status: Literal["open", "in_progress", "done", "abandoned"]
    owner: Literal["planner", "executor"]
    depends_on: list[str] = Field(default_factory=list)
    result_ref: str | None = None
    attempt_count: int = 0
    original_goal: str | None = None
    hard_constraints: list[str] = Field(default_factory=list)


class InteractionResult(BaseModel):
    """Append-only tool interaction result."""

    result_id: str
    kind: Literal["pytest_run", "py_compile", "syntax_check"]
    passed: bool
    failed_tests: list[str] = Field(default_factory=list)
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    linked_subtask: str = ""
    timestamp: datetime


class ToolResultEntry(BaseModel):
    """Append-only truncated tool output for interactive prompt channel (FI-2)."""

    entry_id: str
    session_id: str
    turn_floor: int
    tool: str
    path: str
    truncated_output: str
    ok: bool
    timestamp: datetime


class RetrievalItem(BaseModel):
    """Retrieval index row referencing an L2 record."""

    item_ref: str
    text_summary: str
    importance: float
    written_at: datetime
    last_accessed: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _importance_for_kind(kind: str) -> float:
    if kind in ("reflection", "quality_failure", "terminate"):
        return 1.0
    return 0.5


class RetrievalIndex:
    """Persisted retrieval index backed by MemoryBackend."""

    def __init__(self, backend: MemoryBackend) -> None:
        self._backend = backend

    def append(self, item: RetrievalItem) -> None:
        self._backend.append(STORE_RETRIEVAL, _dump(item))

    def list_items(self) -> list[RetrievalItem]:
        rows = self._backend.query(STORE_RETRIEVAL, {})
        return [RetrievalItem.model_validate(row) for row in rows]

    def count(self) -> int:
        return len(self.list_items())


class StateStore:
    """Versioned state snapshots — never overwrite existing steps."""

    def __init__(
        self,
        backend: MemoryBackend,
        on_index: Callable[[RetrievalItem], None],
    ) -> None:
        self._backend = backend
        self._on_index = on_index

    def write(self, entry: StateEntry) -> StateEntry:
        """Write a new snapshot; assigns step_index if needed."""
        existing = self._backend.query(STORE_STATE, {"session_id": entry.session_id})
        step_index = len(existing)
        if entry.step_index != step_index:
            entry = entry.model_copy(update={"step_index": step_index})
        key = f"{entry.session_id}:{entry.step_index}"
        self._backend.write(STORE_STATE, key, _dump(entry))
        now = _utc_now()
        self._on_index(
            RetrievalItem(
                item_ref=f"state:{entry.step_index}",
                text_summary=(
                    f"State step {entry.step_index} "
                    f"tests={entry.tests_status} "
                    f"open={entry.open_subtasks}"
                ),
                importance=0.5,
                written_at=now,
                last_accessed=now,
            )
        )
        return entry

    def list_for_session(self, session_id: str) -> list[StateEntry]:
        rows = self._backend.query(STORE_STATE, {"session_id": session_id})
        entries = [StateEntry.model_validate(r) for r in rows]
        return sorted(entries, key=lambda e: e.step_index)


class DecisionLog:
    """Append-only decision log."""

    def __init__(
        self,
        backend: MemoryBackend,
        on_index: Callable[[RetrievalItem], None],
        on_append: Callable[[DecisionEntry], None] | None = None,
    ) -> None:
        self._backend = backend
        self._on_index = on_index
        self._on_append = on_append

    def append(self, entry: DecisionEntry) -> DecisionEntry:
        self._backend.append(STORE_DECISIONS, _dump(entry))
        now = _utc_now()
        self._on_index(
            RetrievalItem(
                item_ref=f"decision:{entry.decision_id}",
                text_summary=f"{entry.kind}: {entry.rationale}",
                importance=_importance_for_kind(entry.kind),
                written_at=now,
                last_accessed=now,
            )
        )
        if self._on_append is not None:
            self._on_append(entry)
        return entry

    def get_last_n(self, session_id: str, n: int) -> list[DecisionEntry]:
        rows = self._backend.query(STORE_DECISIONS, {"session_id": session_id})
        entries = [DecisionEntry.model_validate(r) for r in rows]
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:n]

    def list_for_session(self, session_id: str) -> list[DecisionEntry]:
        rows = self._backend.query(STORE_DECISIONS, {"session_id": session_id})
        entries = [DecisionEntry.model_validate(r) for r in rows]
        return sorted(entries, key=lambda e: e.timestamp)


class SubTaskRegistry:
    """Subtasks mutable only via set_status."""

    def __init__(
        self,
        backend: MemoryBackend,
        on_index: Callable[[RetrievalItem], None],
    ) -> None:
        self._backend = backend
        self._on_index = on_index

    def register(self, task: SubTask) -> SubTask:
        self._backend.write(STORE_SUBTASKS, task.task_id, _dump(task))
        now = _utc_now()
        self._on_index(
            RetrievalItem(
                item_ref=f"subtask:{task.task_id}",
                text_summary=f"Subtask {task.task_id}: {task.description}",
                importance=0.5,
                written_at=now,
                last_accessed=now,
            )
        )
        return task

    def get(self, task_id: str) -> SubTask | None:
        row = self._backend.read(STORE_SUBTASKS, task_id)
        if row is None:
            return None
        return SubTask.model_validate(row)

    def get_session_anchor(self, session_id: str) -> tuple[str, list[str]]:
        """Return goal and constraints from the session root subtask, if any."""
        rows = self._backend.query(STORE_SUBTASKS, {"parent_session_id": session_id})
        for row in rows:
            task = SubTask.model_validate(row)
            if task.original_goal:
                return task.original_goal, list(task.hard_constraints)
        return "", []

    def set_status(
        self,
        task_id: str,
        new_status: Literal["open", "in_progress", "done", "abandoned"],
    ) -> SubTask:
        """Transition subtask status; invalid transitions raise ValueError."""
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"Unknown subtask: {task_id}")
        transition = (task.status, new_status)
        if transition not in _VALID_SUBTASK_TRANSITIONS:
            raise ValueError(
                f"Invalid status transition: {task.status} -> {new_status}"
            )
        updated = task.model_copy(update={"status": new_status})
        self._backend.write(STORE_SUBTASKS, task_id, _dump(updated))
        now = _utc_now()
        self._on_index(
            RetrievalItem(
                item_ref=f"subtask:{task_id}",
                text_summary=f"Subtask {task_id} status -> {new_status}",
                importance=0.5,
                written_at=now,
                last_accessed=now,
            )
        )
        return updated


class ToolResultLog:
    """Append-only typed tool outputs for interactive working memory."""

    def __init__(self, backend: MemoryBackend) -> None:
        self._backend = backend

    def append(self, entry: ToolResultEntry) -> ToolResultEntry:
        """Persist one truncated tool result."""
        self._backend.append(STORE_TOOL_RESULTS, _dump(entry))
        return entry

    def list_for_turn(self, session_id: str, turn_floor: int) -> list[ToolResultEntry]:
        """Return tool results for a session turn (matching ``turn_floor``)."""
        rows = self._backend.query(STORE_TOOL_RESULTS, {"session_id": session_id})
        entries = [ToolResultEntry.model_validate(r) for r in rows]
        filtered = [e for e in entries if e.turn_floor == turn_floor]
        return sorted(filtered, key=lambda e: e.timestamp)


class ResultStore:
    """Append-only interaction results."""

    def __init__(
        self,
        backend: MemoryBackend,
        on_index: Callable[[RetrievalItem], None],
    ) -> None:
        self._backend = backend
        self._on_index = on_index

    def append(self, result: InteractionResult) -> InteractionResult:
        self._backend.append(STORE_RESULTS, _dump(result))
        now = _utc_now()
        self._on_index(
            RetrievalItem(
                item_ref=f"result:{result.result_id}",
                text_summary=(
                    f"Result {result.kind} passed={result.passed} "
                    f"subtask={result.linked_subtask}"
                ),
                importance=1.0 if not result.passed else 0.5,
                written_at=now,
                last_accessed=now,
            )
        )
        return result

    def list_for_subtask(self, linked_subtask: str) -> list[InteractionResult]:
        rows = self._backend.query(STORE_RESULTS, {"linked_subtask": linked_subtask})
        return [InteractionResult.model_validate(r) for r in rows]


class WorkingMemory(BaseModel):
    """L1 working memory assembled for each LLM call."""

    original_goal: str
    hard_constraints: list[str]
    agent_role: str
    agent_scope: str
    current_subtask: str
    subtask_id: str
    retrieved_items: list[str] = Field(default_factory=list)
    tool_results: list[ToolResultEntry] = Field(default_factory=list)
    recent_turn_recap: list[str] = Field(default_factory=list)
    last_error: str | None = None
    retry_count: int = 0
    skill_card: str | None = None

    def to_prompt_prefix(self) -> str:
        """Serialize anchor-first prompt prefix (goal + constraints always first)."""
        lines = [
            f"[GOAL]: {self.original_goal}",
            f"[CONSTRAINTS]: {', '.join(self.hard_constraints) if self.hard_constraints else 'none'}",
            f"[ROLE]: {self.agent_role}",
            f"[SCOPE]: {self.agent_scope}",
            f"[CURRENT TASK]: {self.current_subtask}",
            f"[SUBTASK ID]: {self.subtask_id}",
        ]
        if self.retrieved_items:
            lines.append("[CONTEXT]:")
            lines.extend(f"- {item}" for item in self.retrieved_items)
        if self.tool_results:
            lines.append("[TOOL RESULTS] (most recent first):")
            for entry in reversed(self.tool_results):
                status = "ok" if entry.ok else "fail"
                header = f"- {entry.tool}({entry.path}): {status}"
                lines.append(header)
                if entry.truncated_output:
                    lines.append(entry.truncated_output)
        if self.recent_turn_recap:
            lines.append("[RECENT TURNS]:")
            lines.extend(f"- {line}" for line in self.recent_turn_recap)
        if self.last_error:
            lines.append(f"[LAST ERROR]: {self.last_error}")
        if self.retry_count:
            lines.append(f"[RETRY COUNT]: {self.retry_count}")
        if self.skill_card:
            lines.append(f"[GUIDANCE]: {self.skill_card}")
        return "\n".join(lines)

    def token_count(self) -> int:
        """Rough token estimate: len(text) // 4."""
        return len(self.to_prompt_prefix()) // 4


class MemoryStores:
    """Facade over four L2 stores and the retrieval index."""

    def __init__(
        self,
        backend: MemoryBackend,
        *,
        on_decision: Callable[[DecisionEntry], None] | None = None,
    ) -> None:
        self.backend = backend
        self.retrieval = RetrievalIndex(backend)
        self._index_cb: Callable[[RetrievalItem], None] = self.retrieval.append
        self.state = StateStore(backend, self._index_cb)
        self.decisions = DecisionLog(backend, self._index_cb, on_append=on_decision)
        self.subtasks = SubTaskRegistry(backend, self._index_cb)
        self.results = ResultStore(backend, self._index_cb)
        self.tool_results = ToolResultLog(backend)

    @classmethod
    def sqlite(
        cls,
        db_path: str | Path,
        *,
        on_decision: Callable[[DecisionEntry], None] | None = None,
    ) -> MemoryStores:
        """Construct stores with a SQLite backend."""
        return cls(SQLiteBackend(db_path), on_decision=on_decision)


def create_backend_from_env() -> MemoryBackend:
    """Factory using MEMORY_BACKEND and SQLITE_PATH from environment."""
    import os

    from dotenv import load_dotenv

    from framework.memory.backend import RedisBackend

    load_dotenv()
    backend_name = os.getenv("MEMORY_BACKEND", "sqlite").lower()
    if backend_name == "redis":
        return RedisBackend()
    path = os.getenv("SQLITE_PATH", "./data/framework.db")
    return SQLiteBackend(path)

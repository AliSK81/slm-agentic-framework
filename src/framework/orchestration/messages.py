"""Typed Pydantic inter-agent messages."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from framework.memory.backend import MemoryBackend

STORE_DISPATCH = "dispatch_messages"
STORE_REPORT = "report_messages"
STORE_HANDBACK = "handback_messages"


class DispatchMessage(BaseModel):
    """Planner → Executor work assignment."""

    session_id: str
    task_id: str
    subtask_description: str
    memory_slice_keys: list[str] = Field(default_factory=list)
    step_budget: int
    hard_constraints: list[str] = Field(default_factory=list)


class ReportMessage(BaseModel):
    """Executor → Planner completion report."""

    session_id: str
    task_id: str
    outcome: Literal["success", "failure", "partial"]
    new_memory_refs: list[str] = Field(default_factory=list)
    evidence_summary: str


class HandbackMessage(BaseModel):
    """Executor → Planner escalation when blocked."""

    session_id: str
    task_id: str
    reason: str
    blocked_on: str


class TerminateMessage(BaseModel):
    """Session termination summary."""

    session_id: str
    outcome: Literal["solved", "max_steps_reached", "unresolvable"]
    decision_refs: list[str] = Field(default_factory=list)
    result_refs: list[str] = Field(default_factory=list)


def save_dispatch(backend: MemoryBackend, message: DispatchMessage) -> None:
    """Persist latest dispatch message for a session."""
    backend.write(STORE_DISPATCH, message.session_id, message.model_dump(mode="json"))


def load_dispatch(backend: MemoryBackend, session_id: str) -> DispatchMessage | None:
    row = backend.read(STORE_DISPATCH, session_id)
    if row is None:
        return None
    return DispatchMessage.model_validate(row)


def save_report(backend: MemoryBackend, message: ReportMessage) -> None:
    backend.write(STORE_REPORT, message.session_id, message.model_dump(mode="json"))


def load_report(backend: MemoryBackend, session_id: str) -> ReportMessage | None:
    row = backend.read(STORE_REPORT, session_id)
    if row is None:
        return None
    return ReportMessage.model_validate(row)


def save_handback(backend: MemoryBackend, message: HandbackMessage) -> None:
    backend.write(STORE_HANDBACK, message.session_id, message.model_dump(mode="json"))


def load_handback(backend: MemoryBackend, session_id: str) -> HandbackMessage | None:
    row = backend.read(STORE_HANDBACK, session_id)
    if row is None:
        return None
    return HandbackMessage.model_validate(row)

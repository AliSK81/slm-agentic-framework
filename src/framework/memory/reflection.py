"""Verbal reflection on REVISE (Decision Log entry)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

from framework.memory.retrieval import _cap_tokens
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord
from framework.slm.client import SLMClient

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MEMORY_CONFIG = _PROJECT_ROOT / "configs" / "memory.yaml"

REFLECTION_PROMPT = """Task: {original_goal}
Current subtask: {current_subtask}
Attempt {retry_count} failed.
Failure reason: {failure_reason}

In 2-3 sentences: what went wrong, and what specific change should the next attempt make?
Do not repeat what failed. Focus only on what to do differently."""


def _reflection_config() -> dict:
    raw = yaml.safe_load(_MEMORY_CONFIG.read_text(encoding="utf-8"))
    return raw.get("reflection", {})


def _reflection_count(memory: MemoryStores, session_id: str, subtask_id: str) -> int:
    entries = memory.decisions.list_for_session(session_id)
    return sum(
        1
        for e in entries
        if e.kind == "reflection"
        and e.payload.get("linked_subtask") == subtask_id
    )


def write_reflection(
    slm: SLMClient,
    session_id: str,
    step_index: int,
    original_goal: str,
    current_subtask: str,
    retry_count: int,
    failure_reason: str,
    memory: MemoryStores,
    *,
    subtask_id: str | None = None,
) -> str:
    """Call SLM for reflection; append DecisionEntry(kind=reflection)."""
    cfg = _reflection_config()
    max_reflections = int(cfg.get("max_reflections_per_subtask", 3))
    linked = subtask_id or current_subtask

    if _reflection_count(memory, session_id, linked) >= max_reflections:
        logger.info("Reflection cap reached for subtask %s", linked)
        return ""

    prompt = REFLECTION_PROMPT.format(
        original_goal=original_goal,
        current_subtask=current_subtask,
        retry_count=retry_count,
        failure_reason=failure_reason,
    )
    response = slm.call(
        [{"role": "user", "content": prompt}],
        role="planner",
        json_mode=False,
    )
    text = response.content.strip() if not response.error else ""
    if not text:
        text = f"Retry {retry_count}: adjust approach for {current_subtask}."
    max_output_tokens = int(cfg.get("max_output_tokens", 120))
    text = _cap_tokens(text, max_output_tokens)

    entry = DecisionEntry(
        session_id=session_id,
        decision_id=f"d-{uuid.uuid4().hex[:8]}",
        step_index=step_index,
        by_agent="planner",
        kind="reflection",
        payload={"linked_subtask": linked, "text": text},
        rationale=text[:200],
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )
    memory.decisions.append(entry)
    return text

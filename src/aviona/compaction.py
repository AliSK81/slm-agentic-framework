"""Deterministic rolling-context compaction for long Aviona sessions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

BlockKind = Literal["anchor", "turn", "tool_output"]


class HistoryBlock(BaseModel):
    """One segment of rolling REPL context."""

    kind: BlockKind
    text: str


def history_size(history: list[HistoryBlock]) -> int:
    """Total character length of all blocks."""
    return sum(len(block.text) for block in history)


def _protected_blocks(history: list[HistoryBlock]) -> list[HistoryBlock]:
    """Blocks that must survive compaction (anchor + most recent turn)."""
    protected: list[HistoryBlock] = []
    for block in history:
        if block.kind == "anchor":
            protected.append(block)
            break
    turns = [block for block in history if block.kind == "turn"]
    if turns:
        protected.append(turns[-1])
    return protected


def compact(history: list[HistoryBlock], ceiling: int) -> list[HistoryBlock]:
    """Drop oldest ``tool_output`` blocks until ``history_size`` <= ``ceiling``.

    Pure and deterministic: evicts from the front of the list; never removes the
    anchor or the most recent turn. No LLM summarization.

    Args:
        history: Ordered context blocks oldest-first.
        ceiling: Maximum total characters to retain.

    Returns:
        A new list (input is not mutated).
    """
    working = list(history)
    if history_size(working) <= ceiling:
        return working

    protected = set(id(block) for block in _protected_blocks(working))

    while history_size(working) > ceiling:
        evict_index: int | None = None
        for index, block in enumerate(working):
            if block.kind == "tool_output" and id(block) not in protected:
                evict_index = index
                break
        if evict_index is None:
            break
        working.pop(evict_index)

    return working


def history_to_constraint(history: list[HistoryBlock]) -> str | None:
    """Serialize compacted history for injection as a hard constraint segment."""
    if len(history) <= 1:
        return None
    lines = [f"[{block.kind}] {block.text}" for block in history if block.text.strip()]
    if not lines:
        return None
    return "[SESSION CONTEXT]\n" + "\n---\n".join(lines)

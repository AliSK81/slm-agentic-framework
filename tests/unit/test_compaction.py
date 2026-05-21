"""Aviona rolling-context compaction unit tests."""

from __future__ import annotations

from aviona.compaction import HistoryBlock, anchor_to_constraint, compact, history_size, history_to_constraint


def _anchor(text: str = "anchor") -> HistoryBlock:
    return HistoryBlock(kind="anchor", text=text)


def _turn(text: str) -> HistoryBlock:
    return HistoryBlock(kind="turn", text=text)


def _tool(text: str) -> HistoryBlock:
    return HistoryBlock(kind="tool_output", text=text)


def test_compact_evicts_oldest_tool_output_first() -> None:
    """Oldest tool blobs are removed before newer ones."""
    history = [
        _anchor("A" * 100),
        _tool("tool-1 " + "x" * 2000),
        _tool("tool-2 " + "y" * 2000),
        _tool("tool-3 " + "z" * 2000),
        _turn("latest turn"),
    ]
    ceiling = history_size(history) - 1500
    compacted = compact(history, ceiling)
    assert history_size(compacted) <= ceiling
    texts = [block.text for block in compacted]
    assert "tool-1" not in " ".join(texts)
    assert "tool-3" in " ".join(texts)


def test_compact_keeps_anchor_and_last_turn() -> None:
    """Anchor and the most recent turn always survive compaction."""
    history = [
        _anchor("keep-anchor"),
        _tool("t1 " + "o" * 5000),
        _tool("t2 " + "o" * 5000),
        _turn("keep-last-turn"),
    ]
    compacted = compact(history, ceiling=500)
    kinds = {block.kind for block in compacted}
    assert "anchor" in kinds
    assert "turn" in kinds
    assert any("keep-anchor" in block.text for block in compacted)
    assert any("keep-last-turn" in block.text for block in compacted)


def test_compact_is_deterministic() -> None:
    """Same input history yields the same compacted output."""
    history = [
        _anchor("a"),
        _tool("one"),
        _tool("two"),
        _tool("three"),
        _turn("last"),
    ]
    first = compact(history, ceiling=50)
    second = compact(history, ceiling=50)
    assert [block.model_dump() for block in first] == [
        block.model_dump() for block in second
    ]


def test_anchor_to_constraint_returns_anchor_on_first_turn() -> None:
    """Anchor block is available even when history has only the anchor."""
    text = anchor_to_constraint([_anchor("runtime: model=mock")])
    assert text == "runtime: model=mock"


def test_history_to_constraint_skips_trivial_history() -> None:
    """Only anchor → no session context constraint."""
    assert history_to_constraint([_anchor("only")]) is None


def test_history_to_constraint_serializes_blocks() -> None:
    """Non-trivial history becomes a [SESSION CONTEXT] segment."""
    text = history_to_constraint([_anchor("a"), _turn("user: hi")])
    assert text is not None
    assert text.startswith("[SESSION CONTEXT]")
    assert "turn" in text

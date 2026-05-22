"""Unit tests for semantic vs keyword retrieval (phase 29)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from framework.memory.retrieval import (
    SemanticRetriever,
    estimate_tokens,
    get_retrieval_mode,
    retrieve_top_k,
)
from framework.memory.stores import RetrievalItem


def _item(ref: str, text: str) -> RetrievalItem:
    now = datetime.now(UTC)
    return RetrievalItem(
        item_ref=ref,
        text_summary=text,
        importance=0.5,
        written_at=now,
        last_accessed=now,
    )


def _mock_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic embeddings: ``target`` dimension dominates for matching text."""
    vectors: list[list[float]] = []
    for text in texts:
        if "target" in text.lower():
            vectors.append([1.0, 0.0, 0.0])
        else:
            vectors.append([0.0, 1.0, 0.0])
    return vectors


def test_semantic_retriever_returns_typed_items_capped_150_tokens() -> None:
    """Semantic path returns RetrievalItem rows with text capped at 150 tokens."""
    index = [
        _item("a", "unrelated filler content"),
        _item("b", "target semantic match here"),
    ]
    long_text = "target " + "word " * 200
    index.append(_item("c", long_text))

    retriever = SemanticRetriever(embed_fn=_mock_embed)
    results = retriever.retrieve_top_k(index, "find target concept", k=2)

    assert len(results) == 2
    assert all(isinstance(row, RetrievalItem) for row in results)
    assert results[0].item_ref in {"b", "c"}
    for row in results:
        assert estimate_tokens(row.text_summary) <= 150


def test_retrieval_mode_flag_switches_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """MEMORY_RETRIEVAL_MODE=semantic routes retrieve_top_k through SemanticRetriever."""
    monkeypatch.setenv("MEMORY_RETRIEVAL_MODE", "semantic")
    index = [
        _item("a", "noise"),
        _item("b", "target item wins"),
    ]
    results = retrieve_top_k(
        index,
        "target query",
        k=1,
        embed_fn=_mock_embed,
    )
    assert len(results) == 1
    assert results[0].item_ref == "b"
    assert get_retrieval_mode() == "semantic"


def test_keyword_mode_is_default_and_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default keyword mode still ranks by Generative Agents overlap scoring."""
    monkeypatch.delenv("MEMORY_RETRIEVAL_MODE", raising=False)
    index = [
        _item("a", "fix multiply function"),
        _item("b", "unrelated database schema"),
    ]
    results = retrieve_top_k(index, "multiply fix", k=1)
    assert results[0].item_ref == "a"
    assert get_retrieval_mode() == "keyword"

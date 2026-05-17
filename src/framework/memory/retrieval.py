"""Retrieval index scoring (Generative Agents, Park et al. 2023)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from framework.memory.stores import RetrievalItem

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MEMORY_CONFIG = _PROJECT_ROOT / "configs" / "memory.yaml"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _load_retrieval_config() -> dict[str, float]:
    raw = yaml.safe_load(_MEMORY_CONFIG.read_text(encoding="utf-8"))
    retrieval: dict[str, Any] = raw.get("retrieval", {})
    return {
        "alpha_recency": float(retrieval.get("alpha_recency", 0.2)),
        "alpha_importance": float(retrieval.get("alpha_importance", 0.5)),
        "alpha_relevance": float(retrieval.get("alpha_relevance", 0.3)),
        "decay_factor": float(retrieval.get("decay_factor", 0.995)),
        "top_k": int(retrieval.get("top_k", 3)),
        "max_item_tokens": int(retrieval.get("max_item_tokens", 150)),
    }


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bigrams(words: list[str]) -> list[tuple[str, str]]:
    return [(words[i], words[i + 1]) for i in range(len(words) - 1)]


def keyword_overlap(item: RetrievalItem, query: str) -> float:
    """Bigram hits×2 + word hits×1, normalized to [0, 1]."""
    query_words = _tokenize(query)
    if not query_words:
        return 0.0
    text_words = set(_tokenize(item.text_summary))
    word_hits = sum(1 for w in query_words if w in text_words)
    text_joined = " ".join(_tokenize(item.text_summary))
    bigram_hits = 0
    for bg in _bigrams(query_words):
        phrase = f"{bg[0]} {bg[1]}"
        if phrase in text_joined:
            bigram_hits += 1
    raw = bigram_hits * 2 + word_hits
    denom = max(len(query_words) + max(len(query_words) - 1, 0), 1)
    return min(1.0, raw / denom)


def recency(item: RetrievalItem, now: datetime) -> float:
    """decay_factor ^ hours_since_last_access."""
    cfg = _load_retrieval_config()
    last = item.last_accessed
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    hours = max((now - last).total_seconds() / 3600.0, 0.0)
    return float(cfg["decay_factor"] ** hours)


def score(item: RetrievalItem, query: str, now: datetime | None = None) -> float:
    """Combined retrieval score for one index item."""
    cfg = _load_retrieval_config()
    now = now or datetime.now(UTC)
    rel = keyword_overlap(item, query)
    rec = recency(item, now)
    imp = item.importance
    return (
        cfg["alpha_recency"] * rec
        + cfg["alpha_importance"] * imp
        + cfg["alpha_relevance"] * rel
    )


def _cap_tokens(text: str, max_tokens: int) -> str:
    words = text.split()
    if len(words) <= max_tokens:
        return text
    return " ".join(words[:max_tokens])


def _cap_item(item: RetrievalItem, max_tokens: int) -> RetrievalItem:
    capped = _cap_tokens(item.text_summary, max_tokens)
    if capped == item.text_summary:
        return item
    return item.model_copy(update={"text_summary": capped})


def retrieve_top_k(
    index: list[RetrievalItem],
    query: str,
    k: int | None = None,
    *,
    now: datetime | None = None,
) -> list[RetrievalItem]:
    """Score all items and return top-k (text_summary capped per config)."""
    cfg = _load_retrieval_config()
    k = k if k is not None else cfg["top_k"]
    max_tokens = cfg["max_item_tokens"]
    now = now or datetime.now(UTC)
    ranked = sorted(index, key=lambda item: score(item, query, now), reverse=True)
    return [_cap_item(item, max_tokens) for item in ranked[:k]]

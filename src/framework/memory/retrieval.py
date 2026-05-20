"""Retrieval index scoring — keyword (Generative Agents) or semantic (Chroma)."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from framework.memory.stores import RetrievalItem

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MEMORY_CONFIG = _PROJECT_ROOT / "configs" / "memory.yaml"

_TOKEN_RE = re.compile(r"[a-z0-9]+")

EmbedFn = Callable[[list[str]], list[list[float]]]


def _load_retrieval_config() -> dict[str, Any]:
    raw = yaml.safe_load(_MEMORY_CONFIG.read_text(encoding="utf-8"))
    retrieval: dict[str, Any] = raw.get("retrieval", {})
    return {
        "mode": str(retrieval.get("mode", "keyword")).lower(),
        "alpha_recency": float(retrieval.get("alpha_recency", 0.2)),
        "alpha_importance": float(retrieval.get("alpha_importance", 0.5)),
        "alpha_relevance": float(retrieval.get("alpha_relevance", 0.3)),
        "decay_factor": float(retrieval.get("decay_factor", 0.995)),
        "top_k": int(retrieval.get("top_k", 3)),
        "max_item_tokens": int(retrieval.get("max_item_tokens", 150)),
    }


def get_retrieval_mode() -> str:
    """Resolve retrieval mode from env (``MEMORY_RETRIEVAL_MODE``) or memory.yaml."""
    env = os.getenv("MEMORY_RETRIEVAL_MODE", "").strip().lower()
    if env in ("keyword", "semantic"):
        return env
    return str(_load_retrieval_config()["mode"])


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
    word_hits = sum(1 for word in query_words if word in text_words)
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
    """Combined keyword retrieval score for one index item."""
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


def _keyword_retrieve_top_k(
    index: list[RetrievalItem],
    query: str,
    k: int,
    *,
    now: datetime | None = None,
) -> list[RetrievalItem]:
    cfg = _load_retrieval_config()
    max_tokens = cfg["max_item_tokens"]
    now = now or datetime.now(UTC)
    ranked = sorted(index, key=lambda item: score(item, query, now), reverse=True)
    return [_cap_item(item, max_tokens) for item in ranked[:k]]


def _default_sentence_embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with sentence-transformers (lazy model load)."""
    from sentence_transformers import SentenceTransformer

    if not hasattr(_default_sentence_embed, "_model"):
        _default_sentence_embed._model = SentenceTransformer(  # type: ignore[attr-defined]
            "all-MiniLM-L6-v2"
        )
    model = _default_sentence_embed._model  # type: ignore[attr-defined]
    vectors = model.encode(texts, convert_to_numpy=True)
    return [vector.tolist() for vector in vectors]


class SemanticRetriever:
    """Chroma-backed semantic retrieval with the same top-k contract as keyword mode."""

    def __init__(self, *, embed_fn: EmbedFn | None = None) -> None:
        self._embed_fn = embed_fn or _default_sentence_embed

    def retrieve_top_k(
        self,
        index: list[RetrievalItem],
        query: str,
        k: int,
    ) -> list[RetrievalItem]:
        """Rank items by embedding similarity to the query via an ephemeral Chroma collection."""
        if not index:
            return []
        cfg = _load_retrieval_config()
        max_tokens = cfg["max_item_tokens"]
        k = min(k, len(index))

        import chromadb

        client = chromadb.EphemeralClient()
        collection = client.create_collection(
            name=f"wm_{uuid4_hex()}",
            metadata={"hnsw:space": "cosine"},
        )

        ids = [item.item_ref for item in index]
        documents = [item.text_summary for item in index]
        embeddings = self._embed_fn(documents)
        collection.add(ids=ids, documents=documents, embeddings=embeddings)

        query_embedding = self._embed_fn([query])[0]
        hits = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
        )
        hit_ids = (hits.get("ids") or [[]])[0]
        by_id = {item.item_ref: item for item in index}
        ordered = [by_id[item_id] for item_id in hit_ids if item_id in by_id]
        return [_cap_item(item, max_tokens) for item in ordered]


def uuid4_hex() -> str:
    """Short unique suffix for ephemeral Chroma collection names."""
    import uuid

    return uuid.uuid4().hex


def retrieve_top_k(
    index: list[RetrievalItem],
    query: str,
    k: int | None = None,
    *,
    now: datetime | None = None,
    mode: str | None = None,
    embed_fn: EmbedFn | None = None,
) -> list[RetrievalItem]:
    """Score all items and return top-k (text_summary capped per config).

    Dispatches to keyword (Generative Agents) or semantic (Chroma) based on
    ``mode``, ``MEMORY_RETRIEVAL_MODE``, or ``memory.yaml`` ``retrieval.mode``.
    """
    cfg = _load_retrieval_config()
    k = k if k is not None else cfg["top_k"]
    resolved = (mode or get_retrieval_mode()).lower()
    if resolved == "semantic":
        retriever = SemanticRetriever(embed_fn=embed_fn)
        return retriever.retrieve_top_k(index, query, k)
    if resolved != "keyword":
        logger.warning("Unknown retrieval mode %r; using keyword", resolved)
    return _keyword_retrieve_top_k(index, query, k, now=now)

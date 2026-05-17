"""Keyword codebase search for SWE-bench style tasks."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class CodeChunk(BaseModel):
    """A matched region of source code."""

    file: str
    line_start: int
    line_end: int
    text: str


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bigrams(words: list[str]) -> list[tuple[str, str]]:
    return [(words[i], words[i + 1]) for i in range(len(words) - 1)]


def _score_chunk(query_words: list[str], chunk_words: list[str]) -> float:
    if not query_words:
        return 0.0
    word_hits = sum(1 for w in query_words if w in set(chunk_words))
    chunk_text = " ".join(chunk_words)
    bigram_hits = sum(
        1 for bg in _bigrams(query_words) if f"{bg[0]} {bg[1]}" in chunk_text
    )
    raw = bigram_hits * 2 + word_hits
    denom = max(len(query_words) + max(len(query_words) - 1, 0), 1)
    return raw / denom


def build_keyword_index(workspace: Path) -> dict[str, list[dict]]:
    """Index all .py files by file path and line-window chunks."""
    workspace = workspace.resolve()
    index: dict[str, list[dict]] = {}
    for path in workspace.rglob("*.py"):
        if not path.is_file():
            continue
        rel = path.relative_to(workspace).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        chunks: list[dict] = []
        window = 5
        for start in range(0, max(len(lines), 1), window):
            end = min(start + window, len(lines))
            text = "\n".join(lines[start:end])
            chunks.append(
                {
                    "line_start": start + 1,
                    "line_end": end,
                    "text": text[:200],
                    "words": _tokenize(text),
                }
            )
        index[rel] = chunks
    return index


def search_codebase(
    query: str,
    index: dict[str, list[dict]],
    top_k: int = 3,
) -> list[CodeChunk]:
    """Keyword overlap scoring; return top-k chunks (text truncated to 200 chars)."""
    query_words = _tokenize(query)
    scored: list[tuple[float, CodeChunk]] = []
    for file_path, chunks in index.items():
        for chunk in chunks:
            score = _score_chunk(query_words, chunk["words"])
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    CodeChunk(
                        file=file_path,
                        line_start=chunk["line_start"],
                        line_end=chunk["line_end"],
                        text=str(chunk["text"])[:200],
                    ),
                )
            )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]

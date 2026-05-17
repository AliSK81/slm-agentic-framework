"""Asymmetric tool output truncation."""

from __future__ import annotations

CAPS: dict[str, int] = {
    "pytest_run": 4000,
    "py_compile": 2000,
    "read_file": 8000,
    "syntax_check": 1500,
    "search_codebase": 2000,
}


def truncate(text: str, tool: str) -> str:
    """Apply cap for tool. Asymmetric: head=75%, tail=25% of cap."""
    cap = CAPS.get(tool, 4000)
    if len(text) <= cap:
        return text
    head_len = int(cap * 0.75)
    tail_len = cap - head_len
    if tail_len <= 0:
        return text[:cap]
    return text[:head_len] + text[-tail_len:]

"""Sanitize SLM-produced Python source before writing to disk."""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^```(?:python)?\s*\n?", re.IGNORECASE)
_TRAILING_JSON_LINE = re.compile(r"^\s*[\}\],]+,?\s*$")


def sanitize_python_source(text: str) -> str:
    """Remove markdown fences and trailing JSON closure lines from model output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and _FENCE_RE.match(lines[0]):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    lines = cleaned.splitlines()
    while lines and _TRAILING_JSON_LINE.match(lines[-1]):
        lines.pop()

    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"

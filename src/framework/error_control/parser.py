"""Repair and parse SLM JSON decision output."""

from __future__ import annotations

import ast
import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_TOOL_FENCE_RE = re.compile(r"```tool\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_DECISION_TAG_RE = re.compile(r"<decision>\s*(.*?)\s*</decision>", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_SINGLE_QUOTED_KEY_RE = re.compile(r"'([^']+)'\s*:")


def _extract_candidates(raw_text: str) -> list[str]:
    """Collect JSON payload candidates from known SLM wrappers."""
    candidates: list[str] = []
    for pattern in (_JSON_FENCE_RE, _TOOL_FENCE_RE, _DECISION_TAG_RE):
        for match in pattern.finditer(raw_text):
            candidates.append(match.group(1).strip())
    stripped = raw_text.strip()
    if "{" in stripped:
        start = stripped.find("{")
        candidates.append(stripped[start:])
    if stripped.startswith("{"):
        candidates.append(stripped)
    return candidates


def _repair_json(text: str) -> str:
    """Apply deterministic repairs for common malformed JSON patterns."""
    repaired = text.strip()
    repaired = _TRAILING_COMMA_RE.sub(r"\1", repaired)
    repaired = _SINGLE_QUOTED_KEY_RE.sub(r'"\1":', repaired)
    repaired = repaired.replace("\r\n", "\\n").replace("\n", "\\n")
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    if open_braces > 0:
        repaired += "}" * open_braces
    if open_brackets > 0:
        repaired += "]" * open_brackets
    return repaired


def _try_parse(text: str, schema: type[T]) -> T | None:
    try:
        data = json.loads(text)
        return schema.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        logger.debug("json parse failed: %s", exc)
    try:
        literal: Any = ast.literal_eval(text)
        if isinstance(literal, dict):
            return schema.model_validate(literal)
    except (SyntaxError, ValidationError, TypeError, ValueError) as exc:
        logger.debug("literal_eval failed: %s", exc)
    return None


def parse_decision(raw_text: str, schema: type[T]) -> T | None:
    """Try native parse → extract → repair → validate schema → return or None."""
    if not raw_text or not raw_text.strip():
        return None

    attempts: list[str] = []
    attempts.extend(_extract_candidates(raw_text))
    attempts.append(raw_text.strip())

    seen: set[str] = set()
    for candidate in attempts:
        if candidate in seen:
            continue
        seen.add(candidate)
        parsed = _try_parse(candidate, schema)
        if parsed is not None:
            return parsed
        repaired = _repair_json(candidate)
        if repaired not in seen:
            seen.add(repaired)
            parsed = _try_parse(repaired, schema)
            if parsed is not None:
                return parsed
    return None

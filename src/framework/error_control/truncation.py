"""Asymmetric tool output truncation."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TRUNCATION_CONFIG = _PROJECT_ROOT / "configs" / "truncation.yaml"

_BUILTIN_DEFAULTS: dict[str, int] = {
    "pytest_run": 4000,
    "py_compile": 2000,
    "read_file": 8000,
    "syntax_check": 1500,
    "search_codebase": 2000,
}

_active_profile = "default"

# Mutable view used by legacy imports and tests.
CAPS: dict[str, int] = dict(_BUILTIN_DEFAULTS)


@lru_cache(maxsize=1)
def _load_truncation_raw() -> dict[str, Any]:
    """Load ``configs/truncation.yaml`` once."""
    if not _TRUNCATION_CONFIG.is_file():
        return {}
    try:
        return yaml.safe_load(_TRUNCATION_CONFIG.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        logger.warning("Could not read truncation config: %s", exc)
        return {}


def get_caps(profile: str | None = None) -> dict[str, int]:
    """Return per-tool caps for ``profile`` (defaults to the active profile)."""
    name = profile or _active_profile
    raw = _load_truncation_raw()
    profiles: dict[str, Any] = raw.get("profiles", {})
    merged = dict(_BUILTIN_DEFAULTS)
    profile_caps = profiles.get(name) or profiles.get("default") or {}
    if isinstance(profile_caps, dict):
        for key, value in profile_caps.items():
            if isinstance(value, int):
                merged[str(key)] = value
    return merged


def set_caps_profile(profile: str) -> None:
    """Switch the active truncation profile and refresh module ``CAPS``."""
    global _active_profile
    _active_profile = profile
    CAPS.clear()
    CAPS.update(get_caps(profile))


def get_compaction_ceiling() -> int:
    """Character ceiling for rolling context compaction."""
    raw = _load_truncation_raw()
    compaction = raw.get("compaction") or {}
    ceiling = compaction.get("context_ceiling_chars", 12000)
    return int(ceiling) if isinstance(ceiling, int) else 12000


def truncate(text: str, tool: str) -> str:
    """Apply cap for tool. Asymmetric: head=75%, tail=25% of cap."""
    cap = CAPS.get(tool, CAPS.get("pytest_run", 4000))
    if len(text) <= cap:
        return text
    head_len = int(cap * 0.75)
    tail_len = cap - head_len
    if tail_len <= 0:
        return text[:cap]
    return text[:head_len] + text[-tail_len:]

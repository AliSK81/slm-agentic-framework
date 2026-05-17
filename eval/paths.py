"""Safe path helpers for evaluation artifacts."""

from __future__ import annotations

import re

_UNSAFE = re.compile(r"[^\w\-.]+")


def safe_task_slug(task_id: str) -> str:
    """Convert a benchmark task id into a filesystem-safe slug."""
    slug = _UNSAFE.sub("_", task_id.strip())
    return slug.strip("_") or "task"

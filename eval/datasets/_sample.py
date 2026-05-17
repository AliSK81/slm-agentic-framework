"""Shared dataset sampling helpers."""

from __future__ import annotations

import random
from typing import TypeVar

T = TypeVar("T")


def sample_items(items: list[T], n: int, seed: int) -> list[T]:
    """Return up to ``n`` items using a deterministic RNG sample."""
    if n <= 0:
        return []
    if n >= len(items):
        return list(items)
    rng = random.Random(seed)
    return rng.sample(items, n)

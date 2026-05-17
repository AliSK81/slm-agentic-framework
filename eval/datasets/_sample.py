"""Shared dataset sampling helpers."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_STRATA = ("easy", "medium", "hard")


def sample_items(items: list[T], n: int, seed: int) -> list[T]:
    """Return up to ``n`` items using a deterministic RNG sample."""
    if n <= 0:
        return []
    if n >= len(items):
        return list(items)
    rng = random.Random(seed)
    return rng.sample(items, n)


def _bucket_key(value: str) -> str:
    """Deterministic pseudo-difficulty bucket when labels are unavailable."""
    return _STRATA[hash(value) % len(_STRATA)]


def sample_stratified(
    items: list[T],
    difficulty_split: dict[str, int],
    seed: int,
    *,
    key_fn: Callable[[T], str],
) -> list[T]:
    """Sample per stratum using counts from ``difficulty_split``."""
    buckets: dict[str, list[T]] = {name: [] for name in _STRATA}
    for item in items:
        bucket = _bucket_key(key_fn(item))
        buckets[bucket].append(item)

    rng = random.Random(seed)
    selected: list[T] = []
    for stratum, count in difficulty_split.items():
        if count <= 0:
            continue
        pool = buckets.get(stratum, [])
        if not pool:
            continue
        take = min(count, len(pool))
        selected.extend(rng.sample(pool, take))
    return selected


def resolve_sample_count(
    requested_n: int,
    difficulty_split: dict[str, int] | None,
) -> tuple[int, dict[str, int] | None]:
    """Align ``n`` with configured stratum counts when a split is provided."""
    if not difficulty_split:
        return requested_n, None
    split_total = sum(difficulty_split.values())
    if split_total <= 0:
        return requested_n, None
    if requested_n == split_total:
        return requested_n, difficulty_split
    scale = requested_n / split_total
    scaled = {
        stratum: max(0, int(round(count * scale)))
        for stratum, count in difficulty_split.items()
    }
    delta = requested_n - sum(scaled.values())
    if delta and scaled:
        first = next(iter(scaled))
        scaled[first] = max(0, scaled[first] + delta)
    return requested_n, scaled

"""95% confidence intervals for means across seeds (no scipy)."""

from __future__ import annotations

import math
import statistics
from typing import TypedDict


class MeanCI95(TypedDict):
    """Mean and two-sided 95% CI bounds for a small sample."""

    mean: float
    ci_low: float
    ci_high: float
    margin: float
    n: int


# Two-sided 95% t critical values (df = n - 1) for small samples.
_T_CRITICAL_95: dict[int, float] = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    15: 2.131,
    20: 2.086,
    25: 2.060,
    29: 2.045,
}


def _t_critical(df: int) -> float:
    if df <= 0:
        return 0.0
    if df >= 30:
        return 1.96
    return _T_CRITICAL_95.get(df, 2.0)


def mean_ci_95(values: list[float]) -> MeanCI95:
    """Compute sample mean and 95% CI margin (t-based for n < 30)."""
    n = len(values)
    if n == 0:
        return MeanCI95(mean=0.0, ci_low=0.0, ci_high=0.0, margin=0.0, n=0)
    mean = statistics.mean(values)
    if n == 1:
        return MeanCI95(mean=mean, ci_low=mean, ci_high=mean, margin=0.0, n=1)
    stdev = statistics.stdev(values)
    se = stdev / math.sqrt(n)
    margin = _t_critical(n - 1) * se
    return MeanCI95(
        mean=mean,
        ci_low=mean - margin,
        ci_high=mean + margin,
        margin=margin,
        n=n,
    )


def format_mean_pm_ci(ci: MeanCI95, *, digits: int = 1) -> str:
    """Format as ``mean ± margin`` for report tables."""
    if ci["n"] < 2:
        return f"{ci['mean']:.{digits}f}"
    return f"{ci['mean']:.{digits}f} ± {ci['margin']:.{digits}f}"

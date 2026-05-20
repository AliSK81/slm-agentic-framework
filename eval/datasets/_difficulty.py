"""Shared difficulty heuristics for HumanEval- and MBPP-shaped tasks."""

from __future__ import annotations

import re
from typing import Literal, Protocol

DifficultyLabel = Literal["easy", "medium", "hard"]

_HARD_KEYWORDS = re.compile(
    r"(dynamic programming|nested loop|O\(n\^2\)|O\(n\*\*2\)|memoization|"
    r"topological sort|dijkstra|backtrack)",
    re.IGNORECASE,
)
_NESTED_LOOP = re.compile(r"for\b[^\n]*:\s*\n\s*for\b", re.MULTILINE)


class DifficultyFields(Protocol):
    """Minimal task surface for difficulty labeling."""

    task_id: str
    prompt: str
    test_code: str


def count_assertions(test_code: str) -> int:
    """Count assertion statements in a test harness."""
    return len(re.findall(r"\bassert\b", test_code))


def has_hard_keyword_signals(prompt: str, test_code: str) -> bool:
    """Detect nested-loop or DP-style signals in prompt or tests."""
    blob = f"{prompt}\n{test_code}"
    return bool(_HARD_KEYWORDS.search(blob)) or bool(_NESTED_LOOP.search(prompt))


def difficulty_score(task: DifficultyFields) -> tuple[int, int, int]:
    """Return a sortable hardness tuple (higher = harder).

    Components: prompt line count, assertion count, hard-keyword flag (0/1).
    """
    prompt_loc = len(task.prompt.splitlines())
    n_assertions = count_assertions(task.test_code)
    kw_flag = 1 if has_hard_keyword_signals(task.prompt, task.test_code) else 0
    return (prompt_loc, n_assertions, kw_flag)


def difficulty_of(
    task: DifficultyFields,
    *,
    curated_ids: frozenset[str] | None = None,
) -> DifficultyLabel:
    """Assign a deterministic difficulty label from prompt/test heuristics.

    Inputs:
        task: Object with ``task_id``, ``prompt``, and ``test_code``.
        curated_ids: Optional frozen set of ids always labeled ``hard``.

    Outputs:
        One of ``easy``, ``medium``, or ``hard``.
    """
    if curated_ids and task.task_id in curated_ids:
        return "hard"

    prompt_loc, n_assertions, kw_flag = difficulty_score(task)
    if prompt_loc > 12 or n_assertions >= 8 or kw_flag:
        return "hard"
    if 6 <= prompt_loc <= 12 or 4 <= n_assertions <= 7:
        return "medium"
    return "easy"

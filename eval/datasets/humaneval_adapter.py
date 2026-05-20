"""HumanEval dataset adapter."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from eval.datasets._curated_ids import load_curated_ids, resolve_ids_path
from eval.datasets._difficulty import DifficultyLabel, difficulty_of as _difficulty_of
from eval.datasets._sample import resolve_sample_count, sample_items, sample_stratified

logger = logging.getLogger(__name__)

_ENTRY_POINT_RE = re.compile(r"def\s+([a-zA-Z_][\w]*)\s*\(")

_CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"
_CURATED_HARD_IDS_PATH = _CONFIGS_DIR / "humaneval_hard_ids.txt"


class HumanEvalTask(BaseModel):
    """One HumanEval programming task."""

    task_id: str
    prompt: str
    test_code: str
    entry_point: str


@lru_cache(maxsize=1)
def _curated_hard_ids() -> frozenset[str]:
    """Load version-controlled HumanEval ids that are always treated as hard."""
    return load_curated_ids(_CURATED_HARD_IDS_PATH)


def difficulty_of(task: HumanEvalTask) -> DifficultyLabel:
    """Assign a deterministic difficulty label from prompt/test heuristics.

    Curated ids in ``configs/humaneval_hard_ids.txt`` always return ``hard``.
    """
    return _difficulty_of(task, curated_ids=_curated_hard_ids())


def _infer_entry_point(prompt: str, declared: str) -> str:
    if declared:
        return declared
    match = _ENTRY_POINT_RE.search(prompt)
    if match:
        return match.group(1)
    return "candidate"


def _load_humaneval_rows() -> list[HumanEvalTask]:
    """Load the full HumanEval test split from HuggingFace."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("datasets package is required for HumanEval loading") from exc

    dataset = load_dataset("openai/openai_humaneval", split="test")
    rows: list[HumanEvalTask] = []
    for row in dataset:
        entry_point = _infer_entry_point(
            str(row.get("prompt", "")),
            str(row.get("entry_point", "") or ""),
        )
        rows.append(
            HumanEvalTask(
                task_id=str(row["task_id"]),
                prompt=str(row["prompt"]),
                test_code=str(row["test"]),
                entry_point=entry_point,
            )
        )
    return rows


def load_humaneval_curated_hard(
    n: int = 30,
    seed: int = 42,
    *,
    ids_file: str | None = None,
) -> list[HumanEvalTask]:
    """Load the frozen curated hard slice from a version-controlled id list."""
    ids_path = resolve_ids_path(ids_file)
    curated = sorted(load_curated_ids(ids_path))
    if not curated:
        raise ValueError(f"{ids_path} is empty")
    tasks = load_humaneval_by_ids(curated)
    return sample_items(tasks, min(n, len(tasks)), seed)


def load_humaneval_by_ids(task_ids: list[str]) -> list[HumanEvalTask]:
    """Load specific HumanEval tasks by ``task_id`` (order preserved)."""
    lookup = {task.task_id: task for task in _load_humaneval_rows()}
    missing = [task_id for task_id in task_ids if task_id not in lookup]
    if missing:
        raise ValueError(f"Unknown HumanEval task_id(s): {missing}")
    return [lookup[task_id] for task_id in task_ids]


def load_humaneval(
    n: int = 50,
    seed: int = 42,
    *,
    difficulty: str | None = None,
    difficulty_split: dict[str, int] | None = None,
) -> list[HumanEvalTask]:
    """Load HumanEval from HuggingFace; sample ``n`` tasks with ``seed``.

    When ``difficulty`` is set (e.g. ``\"hard\"``), only tasks in that stratum are
    sampled. When ``difficulty_split`` is set and ``difficulty`` is None, tasks are
    bucketed by a deterministic hash of ``task_id`` (legacy stratified behaviour).
    """
    rows = _load_humaneval_rows()

    if difficulty is not None:
        rows = [task for task in rows if difficulty_of(task) == difficulty]
        if not rows:
            raise ValueError(f"No HumanEval tasks with difficulty={difficulty!r}")
        sampled = sample_items(rows, min(n, len(rows)), seed)
        logger.info(
            "Loaded %s HumanEval tasks (difficulty=%s, requested n=%s)",
            len(sampled),
            difficulty,
            n,
        )
        return sampled

    sample_n, split = resolve_sample_count(n, difficulty_split)
    if split:
        sampled = sample_stratified(
            rows,
            split,
            seed,
            key_fn=lambda task: task.task_id,
        )
    else:
        sampled = sample_items(rows, sample_n, seed)
    logger.info("Loaded %s HumanEval tasks (requested n=%s)", len(sampled), n)
    return sampled


def task_solution_stub(task: HumanEvalTask) -> str:
    """Return the HumanEval prompt as an initial ``solution.py`` skeleton."""
    return task.prompt if task.prompt.endswith("\n") else f"{task.prompt}\n"


def task_to_session(task: HumanEvalTask) -> tuple[str, list[str], str]:
    """Map a HumanEval row to session goal, constraints, and pytest body."""
    goal = (
        "Implement the function below in solution.py. "
        "Preserve the signature and docstring.\n\n"
        f"{task.prompt}"
    )
    constraints = [
        f"Entry point must be named '{task.entry_point}'",
        "Write the solution to solution.py",
    ]
    test_code = f"{task.test_code}\ncheck({task.entry_point})"
    return goal, constraints, test_code

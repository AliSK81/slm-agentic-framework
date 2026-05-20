"""HumanEval dataset adapter."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from eval.datasets._sample import resolve_sample_count, sample_items, sample_stratified

logger = logging.getLogger(__name__)

_ENTRY_POINT_RE = re.compile(r"def\s+([a-zA-Z_][\w]*)\s*\(")


class HumanEvalTask(BaseModel):
    """One HumanEval programming task."""

    task_id: str
    prompt: str
    test_code: str
    entry_point: str


def _infer_entry_point(prompt: str, declared: str) -> str:
    if declared:
        return declared
    match = _ENTRY_POINT_RE.search(prompt)
    if match:
        return match.group(1)
    return "candidate"


def load_humaneval(
    n: int = 50,
    seed: int = 42,
    *,
    difficulty_split: dict[str, int] | None = None,
) -> list[HumanEvalTask]:
    """Load HumanEval from HuggingFace; sample ``n`` tasks with ``seed``.

    When ``difficulty_split`` is set (e.g. from configs/eval.yaml), tasks are bucketed
    by a deterministic hash of ``task_id`` into easy/medium/hard strata.
    """
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

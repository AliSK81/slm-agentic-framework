"""HumanEval dataset adapter."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from eval.datasets._sample import sample_items

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


def load_humaneval(n: int = 50, seed: int = 42) -> list[HumanEvalTask]:
    """Load HumanEval from HuggingFace; sample ``n`` tasks with ``seed``.

    Difficulty stratification is not available in the public split; uses uniform sampling.
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

    sampled = sample_items(rows, n, seed)
    logger.info("Loaded %s HumanEval tasks (requested n=%s)", len(sampled), n)
    return sampled


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

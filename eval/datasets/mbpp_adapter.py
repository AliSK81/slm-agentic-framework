"""MBPP dataset adapter."""

from __future__ import annotations

import logging
import re
from pydantic import BaseModel

from eval.datasets._sample import sample_items
from eval.datasets._difficulty import DifficultyLabel, difficulty_of as _difficulty_of

logger = logging.getLogger(__name__)

_ENTRY_POINT_RE = re.compile(r"def\s+([a-zA-Z_][\w]*)\s*\(")


class MBPPTask(BaseModel):
    """One MBPP programming task (same fields as HumanEvalTask)."""

    task_id: str
    prompt: str  # MBPP ``text`` field
    test_code: str  # joined ``test_list`` assertions
    entry_point: str


def _infer_entry_point(code: str, text: str) -> str:
    for blob in (code, text):
        match = _ENTRY_POINT_RE.search(blob)
        if match:
            return match.group(1)
    return "solution"


def _load_mbpp_rows() -> list[MBPPTask]:
    """Load the full MBPP sanitized test split from HuggingFace."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("datasets package is required for MBPP loading") from exc

    dataset = load_dataset("google-research-datasets/mbpp", "sanitized", split="test")
    rows: list[MBPPTask] = []
    for row in dataset:
        text = str(row.get("text", ""))
        code = str(row.get("code", ""))
        test_list = row.get("test_list") or []
        assertions = "\n".join(str(item) for item in test_list)
        entry_point = _infer_entry_point(code, text)
        rows.append(
            MBPPTask(
                task_id=str(row.get("task_id", len(rows))),
                prompt=text if text else code,
                test_code=assertions,
                entry_point=entry_point,
            )
        )
    return rows


def load_mbpp_by_ids(task_ids: list[str]) -> list[MBPPTask]:
    """Load specific MBPP tasks by ``task_id`` (order preserved)."""
    lookup = {str(task.task_id): task for task in _load_mbpp_rows()}
    missing = [task_id for task_id in task_ids if task_id not in lookup]
    if missing:
        raise ValueError(f"Unknown MBPP task_id(s): {missing}")
    return [lookup[task_id] for task_id in task_ids]


def load_mbpp(n: int = 50, seed: int = 42) -> list[MBPPTask]:
    """Load MBPP from HuggingFace; sample ``n`` tasks with ``seed``."""
    rows = _load_mbpp_rows()
    sampled = sample_items(rows, n, seed)
    logger.info("Loaded %s MBPP tasks (requested n=%s)", len(sampled), n)
    return sampled


def difficulty_of(task: MBPPTask) -> DifficultyLabel:
    """Assign a deterministic difficulty label using the same heuristics as HumanEval."""
    return _difficulty_of(task, curated_ids=frozenset())


def task_to_session(task: MBPPTask) -> tuple[str, list[str], str]:
    """Map an MBPP row to session goal, constraints, and pytest body."""
    goal = f"Solve this programming problem in solution.py:\n\n{task.prompt}"
    constraints = [
        f"Primary function name should be '{task.entry_point}'",
        "Write the solution to solution.py",
    ]
    return goal, constraints, task.test_code

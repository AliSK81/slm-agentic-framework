"""SWE-bench dataset adapter (subset loader; execution requires Docker in later phases)."""

from __future__ import annotations

import logging

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SWEBenchTask(BaseModel):
    """One SWE-bench Lite instance (metadata only for Phase 10)."""

    task_id: str
    repo: str
    base_commit: str
    problem_statement: str


def _load_swebench_rows() -> list[SWEBenchTask]:
    """Load the full SWE-bench Lite test split metadata."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("datasets package is required for SWE-bench loading") from exc

    dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    rows: list[SWEBenchTask] = []
    for row in dataset:
        rows.append(
            SWEBenchTask(
                task_id=str(row["instance_id"]),
                repo=str(row["repo"]),
                base_commit=str(row["base_commit"]),
                problem_statement=str(row["problem_statement"]),
            )
        )
    return rows


def load_swebench_by_ids(task_ids: list[str]) -> list[SWEBenchTask]:
    """Load specific SWE-bench Lite tasks by ``task_id`` (order preserved)."""
    lookup = {task.task_id: task for task in _load_swebench_rows()}
    missing = [task_id for task_id in task_ids if task_id not in lookup]
    if missing:
        raise ValueError(f"Unknown SWE-bench task_id(s): {missing}")
    return [lookup[task_id] for task_id in task_ids]


def load_swebench(n: int = 30, seed: int = 42) -> list[SWEBenchTask]:
    """Load a sample of SWE-bench Lite task metadata.

    Full patch verification is deferred to Phase 11+ (Docker required).
    """
    from eval.datasets._sample import sample_items

    rows = _load_swebench_rows()
    sampled = sample_items(rows, n, seed)
    logger.info("Loaded %s SWE-bench Lite tasks (requested n=%s)", len(sampled), n)
    return sampled

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


def load_swebench(n: int = 30, seed: int = 42) -> list[SWEBenchTask]:
    """Load a sample of SWE-bench Lite task metadata.

    Full patch verification is deferred to Phase 11+ (Docker required).
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("datasets package is required for SWE-bench loading") from exc

    from eval.datasets._sample import sample_items

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
    sampled = sample_items(rows, n, seed)
    logger.info("Loaded %s SWE-bench Lite tasks (requested n=%s)", len(sampled), n)
    return sampled

"""Benchmark dataset adapters."""

from eval.datasets.humaneval_adapter import (
    HumanEvalTask,
    difficulty_of,
    load_humaneval,
    load_humaneval_curated_hard,
    task_to_session,
)
from eval.datasets.mbpp_adapter import MBPPTask, load_mbpp
from eval.datasets.mbpp_adapter import task_to_session as mbpp_task_to_session

__all__ = [
    "HumanEvalTask",
    "MBPPTask",
    "difficulty_of",
    "load_humaneval",
    "load_humaneval_curated_hard",
    "load_mbpp",
    "task_to_session",
    "mbpp_task_to_session",
]

# Re-export MBPP mapper under a single name for callers.
mbpp_to_session = mbpp_task_to_session

"""Evaluation metrics and config unit tests (no real benchmark runs)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.config import AblationFlags, EvalConfig, StepBudget, load_eval_config
from eval.datasets._sample import sample_stratified
from eval.datasets.humaneval_adapter import HumanEvalTask
from eval.metrics import RunResult, compute_cer, compute_sr


def _result(
    task_id: str,
    *,
    solved: bool,
    interactions: int = 5,
) -> RunResult:
    return RunResult(
        task_id=task_id,
        solved=solved,
        outcome="solved" if solved else "max_steps_reached",
        interaction_count=interactions,
        step_count=interactions,
        retry_count=0,
        trace_path=f"traces/{task_id}.json",
    )


def test_sr_all_solved() -> None:
    """10 tasks, all solved → SR = 100.0."""
    results = [_result(f"t{i}", solved=True) for i in range(10)]
    assert compute_sr(results) == 100.0


def test_sr_none_solved() -> None:
    """10 tasks, none solved → SR = 0.0."""
    results = [_result(f"t{i}", solved=False) for i in range(10)]
    assert compute_sr(results) == 0.0


def test_cer_all_failed() -> None:
    """10 tasks, all failed → CER = 100.0."""
    results = [_result(f"t{i}", solved=False, interactions=4) for i in range(10)]
    assert compute_cer(results) == 100.0


def test_run_result_schema_valid() -> None:
    """RunResult accepts required fields and rejects missing task_id."""
    row = RunResult(
        task_id="HumanEval/0",
        solved=True,
        outcome="solved",
        interaction_count=3,
        step_count=8,
        retry_count=1,
        trace_path="traces/x.jsonl",
    )
    assert row.task_id == "HumanEval/0"
    with pytest.raises(ValidationError):
        RunResult.model_validate({"solved": True, "outcome": "solved"})


def test_eval_config_loads_from_yaml() -> None:
    """configs/eval.yaml parses into EvalConfig with ablation flags."""
    root = Path(__file__).resolve().parents[2]
    config = load_eval_config(root / "configs" / "eval.yaml")
    assert isinstance(config, EvalConfig)
    assert config.humaneval.get("sample_size") == 50
    assert config.step_budgets["humaneval"] == StepBudget(max_steps=10, max_retries=3)
    assert config.ablation_configs["D"] == AblationFlags(
        memory=True,
        control=True,
        error_control=True,
    )


def test_humaneval_stratified_sample_respects_split() -> None:
    """Stratified sampler returns the configured total when pools are large enough."""
    rows = [
        HumanEvalTask(
            task_id=f"HumanEval/{i}",
            prompt="def f(): pass",
            test_code="def check(c): pass",
            entry_point="f",
        )
        for i in range(100)
    ]
    split = {"easy": 2, "medium": 2, "hard": 1}
    sampled = sample_stratified(rows, split, seed=42, key_fn=lambda t: t.task_id)
    assert len(sampled) == 5

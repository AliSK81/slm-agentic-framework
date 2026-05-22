"""Evaluation metrics and config unit tests (no real benchmark runs)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.config import AblationFlags, EvalConfig, StepBudget, load_eval_config
from eval.datasets._sample import sample_stratified
from eval.datasets.humaneval_adapter import HumanEvalTask
from eval.datasets.mbpp_adapter import MBPPTask, difficulty_of, task_to_session
from eval.metrics import RunResult, compute_cer, compute_sr
from framework.orchestration.session import evaluate_workspace


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
    """configs/runtime/eval.yaml parses into EvalConfig with ablation flags."""
    root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    config = load_eval_config(root / "configs" / "runtime" / "eval.yaml")
    assert isinstance(config, EvalConfig)
    assert config.humaneval.get("sample_size") == 50
    assert config.step_budgets["humaneval"] == StepBudget(max_steps=10, max_retries=3)
    assert config.ablation_configs["D"] == AblationFlags(
        memory=True,
        control=True,
        error_control=True,
        wm_ceiling_override=800,
    )
    assert config.ablation_configs["B"].wm_ceiling_override == 500


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


def test_mbpp_task_maps_to_session_shape() -> None:
    """MBPP task_to_session yields goal, constraints, and test_code for run_full_session."""
    task = MBPPTask(
        task_id="601",
        prompt="Write a function to find the maximum value in a list.",
        test_code="assert max_value([1, 2, 3]) == 3\nassert max_value([-1, 0]) == 0",
        entry_point="max_value",
    )
    goal, constraints, test_code = task_to_session(task)

    assert isinstance(goal, str) and task.prompt in goal
    assert isinstance(constraints, list) and all(isinstance(c, str) for c in constraints)
    assert task.entry_point in constraints[0]
    assert "solution.py" in constraints[1]
    assert isinstance(test_code, str) and "assert max_value" in test_code
    assert difficulty_of(task) in ("easy", "medium", "hard")


def test_mbpp_test_list_compiles_to_pytest(tmp_path: Path) -> None:
    """MBPP assertion lines run as pytest after wrapping in evaluate_workspace."""
    task = MBPPTask(
        task_id="602",
        prompt="Add two integers.",
        test_code="assert add_two(1, 2) == 3\nassert add_two(0, 0) == 0",
        entry_point="add_two",
    )
    _goal, _constraints, test_code = task_to_session(task)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "solution.py").write_text(
        "def add_two(a, b):\n    return a + b\n",
        encoding="utf-8",
    )

    evaluation = evaluate_workspace(workspace, test_code)

    assert evaluation["passed"] is True
    assert evaluation.get("error_message") in (None, "")

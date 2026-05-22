"""Unit tests for ablation runner (dry-run, no API)."""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest

from eval.config import AblationFlags
from eval.scenarios.ablation import (
    AblationResult,
    AblationRunInvalidError,
    ConfigResult,
    SeedRunResult,
    print_comparison_table,
    run_ablation,
)


def test_run_ablation_dry_run_humaneval_small() -> None:
    """Dry-run ablation on 3 tasks returns SR/CER for all four configs."""
    result = run_ablation("humaneval", n=3, seed=42, dry_run=True)
    assert isinstance(result, AblationResult)
    assert result.n_tasks == 3
    assert set(result.configs.keys()) == {"A", "B", "C", "D"}
    for name in "ABCD":
        row = result.configs[name]
        assert row.sr == 0.0
        assert row.cer == 0.0
        assert row.n == 3
        assert len(row.seeds) == 1


def test_print_comparison_table_includes_feature_columns() -> None:
    """Table lists Memory / Control / Error Control per config."""
    result = AblationResult(
        dataset="humaneval",
        n_tasks=5,
        seed=42,
        seeds=[42],
        timestamp="2026-01-01T00:00:00Z",
        configs={
            "A": ConfigResult(sr=10.0, cer=50.0, n=5, n_valid_tasks=5),
            "D": ConfigResult(sr=40.0, cer=20.0, n=5, n_valid_tasks=4),
        },
    )
    flags = {
        "A": AblationFlags(memory=False, control=False, error_control=False),
        "D": AblationFlags(memory=True, control=True, error_control=True),
    }
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_comparison_table(result, flags)
    out = buf.getvalue()
    assert "Memory" in out
    assert "Error Ctrl" in out
    assert "n_valid" in out
    assert "SR mean" in out
    assert "A" in out and "D" in out


def test_ablation_aborts_on_invalid_run() -> None:
    """Non-dry run with run_valid=False aborts the whole ablation."""
    def fake_run_eval(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "sr": 0.0,
            "cer": 100.0,
            "n": 5,
            "n_valid_tasks": 0,
            "trace_file": "traces/x.jsonl",
            "manifest_file": "traces/x.manifest.json",
            "run_valid": False,
            "run_invalid_reason": "too many zero-interaction tasks",
        }

    with patch("eval.scenarios.ablation.run_eval", side_effect=fake_run_eval):
        with pytest.raises(AblationRunInvalidError, match="Run invalid"):
            run_ablation("humaneval_hard", n=5, seeds=[42], dry_run=False)


def test_ablation_aggregates_mean_std_across_seeds() -> None:
    """Multiple seeds produce mean and std SR/CER per config."""
    seed_sr = {41: 10.0, 42: 30.0}

    def fake_run_eval(
        config: str,
        dataset: str,
        *,
        n: int | None = None,
        seed: int = 42,
        dry_run: bool = False,
        **_extra: object,
    ) -> dict[str, object]:
        _ = config, dataset, n, dry_run
        return {
            "sr": seed_sr[seed],
            "cer": 50.0,
            "n": 3,
            "n_valid_tasks": 3,
            "trace_file": f"traces/{seed}.jsonl",
            "manifest_file": f"traces/{seed}.manifest.json",
            "run_valid": True,
        }

    with patch("eval.scenarios.ablation.run_eval", side_effect=fake_run_eval):
        result = run_ablation(
            "humaneval_hard",
            n=3,
            seeds=[41, 42],
            dry_run=True,
        )

    row = result.configs["A"]
    assert row.sr == 20.0
    assert row.sr_std == 10.0
    assert len(row.seeds) == 2
    assert {entry.seed for entry in row.seeds} == {41, 42}


def test_comparison_table_has_feature_and_validity_columns() -> None:
    """Aggregated table includes validity and std columns."""
    result = AblationResult(
        dataset="humaneval_hard",
        n_tasks=30,
        seed=41,
        seeds=[41, 42],
        timestamp="2026-01-01T00:00:00Z",
        configs={
            "D": ConfigResult(
                sr=55.0,
                cer=12.0,
                sr_std=5.0,
                cer_std=2.0,
                n=30,
                n_valid_tasks=28,
                seeds=[
                    SeedRunResult(
                        seed=41,
                        sr=50.0,
                        cer=14.0,
                        n=30,
                        n_valid_tasks=27,
                    ),
                    SeedRunResult(
                        seed=42,
                        sr=60.0,
                        cer=10.0,
                        n=30,
                        n_valid_tasks=29,
                    ),
                ],
            ),
        },
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_comparison_table(result, {"D": AblationFlags(memory=True, control=True, error_control=True)})
    out = buf.getvalue()
    assert "n_valid" in out
    assert "SR std" in out
    assert "CER std" in out
    assert "28" in out


def test_agent_count_one_agent_disables_planner() -> None:
    """Executor-only arm calls run_eval with planner_enabled=False."""
    from eval.scenarios.agent_count import run_agent_count_experiment

    with patch("eval.scenarios.agent_count.run_eval") as mock_run:
        mock_run.return_value = {
            "sr": 0.0,
            "cer": 0.0,
            "n": 3,
            "n_valid_tasks": 0,
            "trace_file": "traces/one.jsonl",
            "manifest_file": "traces/one.manifest.json",
            "run_valid": True,
        }
        run_agent_count_experiment("multistep", n=3, seed=42, dry_run=True)

    planner_flags = [call.kwargs.get("planner_enabled") for call in mock_run.call_args_list]
    assert planner_flags.count(True) == 1
    assert planner_flags.count(False) == 1


def test_agent_count_two_agent_enables_planner() -> None:
    """Two-agent arm runs before one-agent and enables the planner."""
    from eval.scenarios.agent_count import run_agent_count_experiment

    with patch("eval.scenarios.agent_count.run_eval") as mock_run:
        mock_run.return_value = {
            "sr": 50.0,
            "cer": 10.0,
            "n": 2,
            "n_valid_tasks": 2,
            "trace_file": "traces/two.jsonl",
            "manifest_file": "traces/two.manifest.json",
            "run_valid": True,
        }
        result = run_agent_count_experiment("multistep", n=2, seed=7, dry_run=True)

    assert mock_run.call_args_list[0].kwargs["planner_enabled"] is True
    assert result.two_agent.planner_enabled is True
    assert result.two_agent.sr == 50.0


def test_agent_count_reports_cer_per_arm() -> None:
    """Each arm exposes distinct CER values in the structured result."""
    from eval.scenarios.agent_count import run_agent_count_experiment

    def fake_run(
        _config: str,
        _dataset: str,
        *,
        planner_enabled: bool = True,
        **_kwargs: object,
    ) -> dict[str, object]:
        cer = 5.0 if planner_enabled else 25.0
        return {
            "sr": 80.0 if planner_enabled else 60.0,
            "cer": cer,
            "n": 4,
            "n_valid_tasks": 4,
            "trace_file": f"traces/{planner_enabled}.jsonl",
            "manifest_file": "traces/x.manifest.json",
            "run_valid": True,
        }

    with patch("eval.scenarios.agent_count.run_eval", side_effect=fake_run):
        result = run_agent_count_experiment("multistep", n=4, seeds=[42], dry_run=True)

    assert result.two_agent.cer == 5.0
    assert result.one_agent.cer == 25.0
    assert result.two_agent.cer < result.one_agent.cer

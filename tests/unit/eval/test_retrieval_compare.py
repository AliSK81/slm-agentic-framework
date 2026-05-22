"""Unit tests for retrieval_compare scenario (phase 33)."""

from __future__ import annotations

import os
from unittest.mock import patch

from eval.scenarios.retrieval_compare import (
    MEMORY_CONFIGS,
    RETRIEVAL_MODES,
    run_retrieval_compare,
)


def test_retrieval_compare_runs_only_b_and_d() -> None:
    """Only memory-enabled configs B and D are invoked."""
    called: list[tuple[str, str]] = []

    def _fake_run_eval(
        config_name: str,
        dataset_name: str,
        n: int = 30,
        seed: int = 42,
        *,
        dry_run: bool = False,
        planner_enabled: bool = True,
    ) -> dict[str, object]:
        _ = dataset_name, n, seed, dry_run, planner_enabled
        called.append((config_name, os.environ.get("MEMORY_RETRIEVAL_MODE", "")))
        return {
            "sr": 50.0,
            "cer": 25.0,
            "n": 5,
            "trace_file": f"traces/{config_name}_{seed}.jsonl",
            "run_valid": True,
        }

    with patch("eval.scenarios.retrieval_compare.run_eval", side_effect=_fake_run_eval):
        run_retrieval_compare("discriminative", n=5, seeds=[42], dry_run=True)

    configs = {cfg for cfg, _mode in called}
    assert configs == set(MEMORY_CONFIGS)
    assert len(called) == len(MEMORY_CONFIGS) * len(RETRIEVAL_MODES)


def test_retrieval_mode_flag_propagates_to_sessions() -> None:
    """Each mode sets MEMORY_RETRIEVAL_MODE before run_eval."""
    modes_seen: list[str] = []

    def _fake_run_eval(*_args: object, **_kwargs: object) -> dict[str, object]:
        modes_seen.append(os.environ.get("MEMORY_RETRIEVAL_MODE", ""))
        return {"sr": 0.0, "cer": 0.0, "n": 3, "trace_file": "", "run_valid": True}

    with patch("eval.scenarios.retrieval_compare.run_eval", side_effect=_fake_run_eval):
        run_retrieval_compare("discriminative", n=3, seed=42, dry_run=True)

    assert "keyword" in modes_seen
    assert "semantic" in modes_seen


def test_compare_table_has_mode_and_config_columns(capsys) -> None:
    """CLI table includes mode and config columns."""
    from eval.scenarios.retrieval_compare import (
        ModeConfigResult,
        RetrievalCompareResult,
        print_retrieval_table,
    )

    result = RetrievalCompareResult(
        dataset="discriminative",
        n_tasks=5,
        seeds=[42],
        modes={
            "keyword": {
                "B": ModeConfigResult(config="B", sr=10.0, cer=20.0, n=5),
            },
        },
        timestamp="2026-01-01T00:00:00Z",
    )
    print_retrieval_table(result)
    out = capsys.readouterr().out
    assert "Mode" in out and "Config" in out
    assert "keyword" in out and "B" in out

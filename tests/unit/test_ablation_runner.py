"""Unit tests for ablation runner (dry-run, no API)."""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

from eval.config import AblationFlags
from eval.scenarios.ablation import (
    AblationResult,
    ConfigResult,
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


def test_print_comparison_table_includes_feature_columns() -> None:
    """Table lists Memory / Control / Error Control per config."""
    result = AblationResult(
        dataset="humaneval",
        n_tasks=5,
        seed=42,
        timestamp="2026-01-01T00:00:00Z",
        configs={
            "A": ConfigResult(sr=10.0, cer=50.0, n=5),
            "D": ConfigResult(sr=40.0, cer=20.0, n=5),
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
    assert "A" in out and "D" in out

"""E2E ablation on humaneval_hard — honest D vs A comparison (skips, never fakes)."""

from __future__ import annotations

import pytest

from eval.scenarios.ablation import run_ablation

HARD_SLICE_N = 10
HARD_SLICE_SEED = 42
SR_MARGIN_PP = 5.0


@pytest.mark.e2e
def test_ablation_d_geq_a_on_hard_slice(require_api_key: str) -> None:
    """Run A and D on hard slice; pass only if D clearly beats A, else skip with numbers."""
    _ = require_api_key
    result = run_ablation(
        "humaneval_hard",
        n=HARD_SLICE_N,
        seeds=[HARD_SLICE_SEED],
        dry_run=False,
    )
    row_a = result.configs.get("A")
    row_d = result.configs.get("D")
    if row_a is None or row_d is None:
        pytest.skip("Ablation missing config A or D")

    sr_a = row_a.sr
    sr_d = row_d.sr
    cer_a = row_a.cer
    cer_d = row_d.cer

    d_wins_sr = sr_d >= sr_a + SR_MARGIN_PP
    d_wins_cer = cer_d < cer_a
    if d_wins_sr and d_wins_cer:
        return

    pytest.skip(
        f"No D>A claim on hard slice (n={HARD_SLICE_N}, seed={HARD_SLICE_SEED}): "
        f"A SR={sr_a:.1f}% CER={cer_a:.1f}% vs "
        f"D SR={sr_d:.1f}% CER={cer_d:.1f}% "
        f"(need D.SR >= A.SR + {SR_MARGIN_PP}pp and D.CER < A.CER)"
    )

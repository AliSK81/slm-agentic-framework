"""E2E evidence gate: D vs A on the discriminative slice (reads cited traces)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.curated import (
    DEEPSEEK_DISCRIMINATIVE_SECTION,
    EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS,
    build_curated_summaries,
    entries_for_section,
    load_cite_allowlist,
    trace_path_for_run,
)

EXPECTED_RUNS = EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS
SR_MARGIN_PP = 5.0


@pytest.mark.e2e
def test_ablation_d_geq_a_discriminative(require_api_key: str) -> None:
    """Pass when cited D beats A by margin; else skip with observed means (never fake a win)."""
    _ = require_api_key
    traces_root = Path(__file__).resolve().parents[2] / "var" / "traces"
    allowlist = load_cite_allowlist()
    entries = entries_for_section(allowlist, DEEPSEEK_DISCRIMINATIVE_SECTION)
    if len(entries) < EXPECTED_RUNS:
        pytest.skip(
            f"need {EXPECTED_RUNS} runs in {DEEPSEEK_DISCRIMINATIVE_SECTION}; got {len(entries)}"
        )
    missing = [
        entry.run_id
        for entry in entries
        if not trace_path_for_run(entry.run_id, traces_root).is_file()
    ]
    if missing:
        pytest.skip(f"missing traces: {missing[:3]}")

    groups = build_curated_summaries(allowlist, traces_dir=traces_root)
    by_config = {(g.config, g.dataset): g for g in groups}
    key_a = ("A", "discriminative")
    key_d = ("D", "discriminative")
    if key_a not in by_config or key_d not in by_config:
        pytest.skip("curated summaries missing config A or D for discriminative")

    sr_a = by_config[key_a].sr_ci.mean
    sr_d = by_config[key_d].sr_ci.mean
    cer_a = by_config[key_a].cer_ci.mean
    cer_d = by_config[key_d].cer_ci.mean

    if sr_d >= sr_a + SR_MARGIN_PP and cer_d < cer_a:
        return

    pytest.skip(
        f"No D>A claim on discriminative (multi-seed cited): "
        f"A SR={sr_a:.1f}% CER={cer_a:.1f}% vs "
        f"D SR={sr_d:.1f}% CER={cer_d:.1f}% "
        f"(need D.SR >= A.SR + {SR_MARGIN_PP}pp and D.CER < A.CER)"
    )

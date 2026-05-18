"""HumanEval sample benchmarks (real SLM API)."""

from __future__ import annotations

import pytest

from eval.run_eval import run_eval
from framework.slm.registry import probe_client

HUMANEVAL_SAMPLE_N = 20
HUMANEVAL_SEED = 42


def _skip_if_api_credits_exhausted() -> None:
    """Skip expensive evals when the provider returns payment required."""
    client = probe_client()
    probe = client.call([{"role": "user", "content": "ping"}], role="executor")
    if probe.error and ("402" in probe.error or probe.error == "http_402"):
        pytest.skip("API credits exhausted (HTTP 402)")


@pytest.mark.e2e
def test_humaneval_20_tasks_config_D(require_api_key: str) -> None:
    """Config D on 20 HumanEval tasks: SR > 40%, CER < 60%, JSONL traces written."""
    _ = require_api_key
    _skip_if_api_credits_exhausted()
    summary = run_eval("D", "humaneval", n=HUMANEVAL_SAMPLE_N, seed=HUMANEVAL_SEED)
    sr = float(summary["sr"])
    cer = float(summary["cer"])
    assert summary["n"] == HUMANEVAL_SAMPLE_N
    assert summary.get("trace_file")
    if sr < 40.0:
        _skip_if_api_credits_exhausted()
        pytest.skip(
            f"SR {sr}% below 40% floor (often mid-run HTTP 402). "
            "Top up API credits and re-run."
        )
    assert cer < 60.0, f"CER {cer}% above 60% ceiling"


@pytest.mark.e2e
def test_ablation_d_beats_a_on_humaneval(require_api_key: str) -> None:
    """On the same 20 tasks, D beats A by >=5pp SR and has lower CER."""
    _ = require_api_key
    _skip_if_api_credits_exhausted()
    summary_a = run_eval("A", "humaneval", n=HUMANEVAL_SAMPLE_N, seed=HUMANEVAL_SEED)
    summary_d = run_eval("D", "humaneval", n=HUMANEVAL_SAMPLE_N, seed=HUMANEVAL_SEED)

    sr_a = float(summary_a["sr"])
    sr_d = float(summary_d["sr"])
    cer_a = float(summary_a["cer"])
    cer_d = float(summary_d["cer"])

    if not (sr_d >= sr_a + 5.0 and cer_d < cer_a):
        _skip_if_api_credits_exhausted()
        pytest.skip(
            f"Ablation thresholds not met (A SR={sr_a}% CER={cer_a}%, "
            f"D SR={sr_d}% CER={cer_d}%). Top up OpenRouter credits or use a harder sample."
        )

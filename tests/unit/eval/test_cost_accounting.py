"""Unit tests for per-session cost/latency/token accounting (phase 26)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from eval.metrics import RunResult, estimate_cost, load_price_table
from eval.metrics.cost import _row_cost_usd
from framework.orchestration.session import SessionOutcome
from framework.slm.client import SLMClient, SLMResponse
from framework.slm.usage import SLMUsageAccumulator, TrackingSLMClient


def _success_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen/qwen2.5-coder-7b-instruct",
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"total_tokens": 42},
        },
    )


def test_run_result_accumulates_tokens_and_latency() -> None:
    """SessionOutcome usage fields map into RunResult for eval JSONL."""
    session = SessionOutcome(
        session_id="sess-cost",
        outcome="solved",
        tokens_total=300,
        latency_ms_total=90,
        llm_calls=3,
        model_id="qwen/qwen2.5-coder-7b-instruct",
    )
    row = RunResult(
        task_id="HumanEval/1",
        solved=True,
        outcome=session.outcome,
        interaction_count=2,
        step_count=2,
        retry_count=0,
        tokens_total=session.tokens_total,
        latency_ms_total=session.latency_ms_total,
        llm_calls=session.llm_calls,
        model_id=session.model_id,
    )
    assert row.tokens_total == 300
    assert row.latency_ms_total == 90
    assert row.llm_calls == 3


def test_estimate_cost_uses_price_table(tmp_path: Path) -> None:
    """Known model prices produce non-zero estimated USD."""
    trace = tmp_path / "run.jsonl"
    trace.write_text(
        json.dumps(
            RunResult(
                task_id="t1",
                solved=True,
                outcome="solved",
                tokens_total=2000,
                latency_ms_total=500,
                llm_calls=4,
                model_id="qwen/qwen2.5-coder-7b-instruct",
            ).model_dump()
        )
        + "\n",
        encoding="utf-8",
    )
    price_table = {
        "qwen/qwen2.5-coder-7b-instruct": {
            "price_per_1k_in": 0.10,
            "price_per_1k_out": 0.20,
        }
    }
    summary = estimate_cost(trace, price_table)
    expected = _row_cost_usd(2000, price_table["qwen/qwen2.5-coder-7b-instruct"])
    assert summary["tokens_total"] == 2000
    assert summary["latency_ms_total"] == 500
    assert summary["llm_calls"] == 4
    assert summary["estimated_usd"] == round(expected, 6)
    assert summary["estimated_usd"] > 0


def test_estimate_cost_zero_when_price_unknown(tmp_path: Path) -> None:
    """Rows with model ids missing from the price table contribute zero cost."""
    trace = tmp_path / "run.jsonl"
    trace.write_text(
        json.dumps(
            RunResult(
                task_id="t2",
                solved=False,
                outcome="escalate",
                tokens_total=1000,
                model_id="unknown/model",
            ).model_dump()
        )
        + "\n",
        encoding="utf-8",
    )
    summary = estimate_cost(trace, {"known/model": {"price_per_1k_in": 1.0, "price_per_1k_out": 1.0}})
    assert summary["tokens_total"] == 1000
    assert summary["estimated_usd"] == 0.0


def test_llm_call_count_recorded_per_session() -> None:
    """TrackingSLMClient increments llm_calls on every completion."""
    usage = SLMUsageAccumulator()
    transport = httpx.MockTransport(_success_handler)
    inner = SLMClient(
        "qwen2.5-coder-7b-instruct",
        http_client=httpx.Client(transport=transport),
    )
    tracked = TrackingSLMClient(inner, usage)
    try:
        tracked.call([{"role": "user", "content": "json ping"}], role="planner")
        tracked.call([{"role": "user", "content": "json ping"}], role="executor")
    finally:
        tracked.close()
    assert usage.llm_calls == 2
    assert usage.tokens_total == 84
    assert usage.latency_ms_total >= 0


def test_load_price_table_reads_models_yaml() -> None:
    """configs/runtime/models.yaml profiles with price fields appear in the table."""
    table = load_price_table()
    assert "qwen/qwen2.5-coder-7b-instruct" in table
    assert table["qwen/qwen2.5-coder-7b-instruct"]["price_per_1k_in"] > 0

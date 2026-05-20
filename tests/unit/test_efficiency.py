"""Unit tests for efficiency aggregation (phase 34)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from eval.curated import CiteAllowlist, CiteEntry
from eval.manifest import write_manifest
from eval.metrics.efficiency import aggregate_efficiency, format_efficiency_table
from eval.metrics.sr import RunResult


def _write_run_with_usage(
    traces_dir: Path,
    run_id: str,
    *,
    config: str,
    provider: str,
    model_id: str,
    tokens: int,
) -> None:
    rows = [
        RunResult(
            task_id="HumanEval/0",
            solved=True,
            outcome="solved",
            interaction_count=2,
            tokens_total=tokens,
            latency_ms_total=1000,
            llm_calls=3,
            model_id=model_id,
        ).model_dump(),
        RunResult(
            task_id="HumanEval/1",
            solved=False,
            outcome="escalate",
            interaction_count=1,
            tokens_total=tokens // 2,
            latency_ms_total=500,
            llm_calls=2,
            model_id=model_id,
        ).model_dump(),
    ]
    trace = traces_dir / f"{run_id}.jsonl"
    trace.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    write_manifest(
        run_id,
        traces_dir=traces_dir,
        config=config,
        dataset="discriminative",
        n=2,
        seed=42,
        provider=provider,
        planner_profile=model_id,
        executor_profile=model_id,
        git_sha="abc",
        task_ids=["HumanEval/0", "HumanEval/1"],
        created_at=datetime(2026, 5, 21, tzinfo=UTC),
    )


def test_efficiency_aggregates_usage_per_provider_config(tmp_path: Path) -> None:
    """Tokens and latency are averaged per task for each provider × config."""
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_run_with_usage(
        traces,
        "A_discriminative_20260521T100001Z",
        config="A",
        provider="deepseek",
        model_id="deepseek-v4-flash",
        tokens=1000,
    )
    _write_run_with_usage(
        traces,
        "B_discriminative_20260521T100002Z",
        config="B",
        provider="openrouter",
        model_id="qwen/qwen2.5-coder-7b-instruct",
        tokens=400,
    )
    allowlist = CiteAllowlist(
        runs=[
            CiteEntry(run_id="A_discriminative_20260521T100001Z", config="A"),
            CiteEntry(run_id="B_discriminative_20260521T100002Z", config="B"),
        ],
    )
    rows = aggregate_efficiency(allowlist, traces_dir=traces)
    assert len(rows) == 2
    deepseek = next(r for r in rows if r.provider == "deepseek")
    assert deepseek.tokens_per_task > 0
    assert deepseek.config == "A"


def test_estimated_usd_uses_price_table(tmp_path: Path) -> None:
    """Known model prices produce non-zero USD per task."""
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_run_with_usage(
        traces,
        "D_discriminative_20260521T100003Z",
        config="D",
        provider="deepseek",
        model_id="deepseek-v4-flash",
        tokens=2000,
    )
    allowlist = CiteAllowlist(
        runs=[CiteEntry(run_id="D_discriminative_20260521T100003Z", config="D")],
    )
    rows = aggregate_efficiency(allowlist, traces_dir=traces)
    assert rows[0].usd_per_task > 0
    assert rows[0].price_known is True


def test_unknown_price_is_flagged_not_silently_zero(tmp_path: Path) -> None:
    """Models without public pricing flag price_known=false."""
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_run_with_usage(
        traces,
        "B_discriminative_20260521T100004Z",
        config="B",
        provider="openrouter",
        model_id="mistralai/devstral-small",
        tokens=800,
    )
    allowlist = CiteAllowlist(
        runs=[CiteEntry(run_id="B_discriminative_20260521T100004Z", config="B")],
    )
    rows = aggregate_efficiency(allowlist, traces_dir=traces)
    assert rows[0].price_known is False
    table = format_efficiency_table(rows)
    assert "n/a" in table


def test_efficiency_table_compares_deepseek_vs_slm_small(tmp_path: Path) -> None:
    """Table includes both deepseek and openrouter provider rows."""
    traces = tmp_path / "traces"
    traces.mkdir()
    _write_run_with_usage(
        traces,
        "A_discriminative_20260521T100005Z",
        config="A",
        provider="deepseek",
        model_id="deepseek-v4-flash",
        tokens=500,
    )
    _write_run_with_usage(
        traces,
        "A_discriminative_20260521T100006Z",
        config="A",
        provider="openrouter",
        model_id="qwen/qwen2.5-coder-7b-instruct",
        tokens=300,
    )
    allowlist = CiteAllowlist(
        runs=[
            CiteEntry(run_id="A_discriminative_20260521T100005Z"),
            CiteEntry(run_id="A_discriminative_20260521T100006Z"),
        ],
    )
    table = format_efficiency_table(aggregate_efficiency(allowlist, traces_dir=traces))
    assert "deepseek" in table
    assert "openrouter" in table

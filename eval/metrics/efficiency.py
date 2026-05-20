"""Aggregate token, latency, and cost efficiency per provider and config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from eval.curated import CiteAllowlist, iter_cite_entries, load_cite_allowlist, trace_path_for_run
from eval.manifest import RunManifest
from eval.metrics.cost import estimate_cost, load_price_table
from eval.metrics.sr import RunResult


class EfficiencyRow(BaseModel):
    """Per (provider, config) efficiency summary."""

    provider: str
    config: str
    dataset: str
    n_runs: int = 0
    n_tasks: int = 0
    sr_mean: float = 0.0
    cer_mean: float = 0.0
    tokens_per_task: float = 0.0
    latency_ms_per_task: float = 0.0
    llm_calls_per_task: float = 0.0
    usd_per_task: float = 0.0
    price_known: bool = True
    run_ids: list[str] = Field(default_factory=list)


def _load_manifest(trace_path: Path) -> RunManifest | None:
    manifest_path = trace_path.with_name(f"{trace_path.stem}.manifest.json")
    if not manifest_path.is_file():
        return None
    return RunManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))


def aggregate_efficiency(
    allowlist: CiteAllowlist,
    *,
    traces_dir: Path,
    models_path: Path | None = None,
) -> list[EfficiencyRow]:
    """Aggregate usage and estimated cost for cited runs grouped by provider × config."""
    price_table = load_price_table(models_path)
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}

    for entry in iter_cite_entries(allowlist):
        trace_path = trace_path_for_run(entry.run_id, traces_dir)
        if not trace_path.is_file():
            continue
        manifest = _load_manifest(trace_path)
        provider = manifest.provider if manifest else "unknown"
        config = entry.config or (manifest.config if manifest else "?")
        dataset = entry.dataset or (manifest.dataset if manifest else "?")
        key = (provider, config, dataset)
        bucket = buckets.setdefault(
            key,
            {
                "tokens": 0,
                "latency": 0,
                "calls": 0,
                "tasks": 0,
                "usd": 0.0,
                "price_known": True,
                "run_ids": [],
            },
        )
        rows = [
            RunResult.model_validate(json.loads(line))
            for line in trace_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        cost = estimate_cost(trace_path, price_table)
        bucket["tokens"] += int(cost["tokens_total"])
        bucket["latency"] += int(cost["latency_ms_total"])
        bucket["calls"] += int(cost["llm_calls"])
        bucket["tasks"] += len(rows)
        bucket["usd"] += float(cost["estimated_usd"])
        if not cost.get("price_known", True):
            bucket["price_known"] = False
        bucket["run_ids"].append(entry.run_id)

    from eval.metrics import compute_cer, compute_sr

    results: list[EfficiencyRow] = []
    for (provider, config, dataset), bucket in sorted(buckets.items()):
        tasks = max(bucket["tasks"], 1)
        results.append(
            EfficiencyRow(
                provider=provider,
                config=config,
                dataset=dataset,
                n_runs=len(bucket["run_ids"]),
                n_tasks=bucket["tasks"],
                tokens_per_task=bucket["tokens"] / tasks,
                latency_ms_per_task=bucket["latency"] / tasks,
                llm_calls_per_task=bucket["calls"] / tasks,
                usd_per_task=bucket["usd"] / tasks,
                price_known=bool(bucket["price_known"]),
                run_ids=list(bucket["run_ids"]),
            )
        )
    return results


def format_efficiency_table(rows: list[EfficiencyRow]) -> str:
    """Render a markdown table for the efficiency chapter."""
    lines = [
        "## Efficiency (tokens / latency / cost per task)",
        "",
        "| Provider | Config | Dataset | Tasks | Tokens/task | Latency ms/task | "
        "LLM calls/task | $/task | Price known |",
        "|----------|--------|---------|-------|-------------|-----------------|"
        "---------------|--------|-------------|",
    ]
    for row in rows:
        usd = f"{row.usd_per_task:.4f}" if row.price_known else "n/a"
        known = "yes" if row.price_known else "no"
        lines.append(
            f"| {row.provider} | {row.config} | {row.dataset} | {row.n_tasks} | "
            f"{row.tokens_per_task:.1f} | {row.latency_ms_per_task:.1f} | "
            f"{row.llm_calls_per_task:.2f} | {usd} | {known} |"
        )
    if not rows:
        lines.append("| (no cited runs with usage) | | | | | | | | |")
    return "\n".join(lines) + "\n"


def load_efficiency_from_project(
    *,
    traces_dir: Path | None = None,
    allowlist_path: Path | None = None,
) -> list[EfficiencyRow]:
    """Load allowlist and aggregate efficiency for the thesis report."""
    root = Path(__file__).resolve().parents[2]
    return aggregate_efficiency(
        load_cite_allowlist(allowlist_path),
        traces_dir=traces_dir or (root / "traces"),
    )

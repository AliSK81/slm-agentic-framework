"""Estimated run cost from aggregate JSONL traces and model price tables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from eval.metrics.sr import RunResult

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MODELS = _PROJECT_ROOT / "configs" / "models.yaml"


def load_price_table(models_path: Path | None = None) -> dict[str, dict[str, float]]:
    """Build ``model_id -> {price_per_1k_in, price_per_1k_out}`` from profile yaml."""
    path = models_path or _DEFAULT_MODELS
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = raw.get("profiles") or {}
    table: dict[str, dict[str, float]] = {}
    for _name, block in profiles.items():
        if not isinstance(block, dict):
            continue
        model_id = block.get("model_id")
        if not model_id:
            continue
        price_in = float(block.get("price_per_1k_in", 0.0) or 0.0)
        price_out = float(block.get("price_per_1k_out", 0.0) or 0.0)
        if price_in or price_out:
            table[str(model_id)] = {
                "price_per_1k_in": price_in,
                "price_per_1k_out": price_out,
            }
    return table


def _row_cost_usd(tokens: int, prices: dict[str, float]) -> float:
    """Estimate USD for one row using blended in/out rates when only total tokens exist."""
    if tokens <= 0 or not prices:
        return 0.0
    rate_in = float(prices.get("price_per_1k_in", 0.0))
    rate_out = float(prices.get("price_per_1k_out", 0.0))
    blended = (rate_in + rate_out) / 2.0
    return (tokens / 1000.0) * blended


def estimate_cost(
    run_path: str | Path,
    price_table: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """Summarize token/latency totals and estimated USD for an aggregate JSONL run.

    Inputs:
        run_path: Path to JSONL with one :class:`RunResult` per line.
        price_table: ``model_id`` -> ``price_per_1k_in`` / ``price_per_1k_out``; missing
            models contribute zero cost.

    Outputs:
        Dict with ``tokens_total``, ``latency_ms_total``, ``llm_calls``, ``estimated_usd``,
        and per-row ``n``.
    """
    path = Path(run_path).expanduser().resolve()
    rows: list[RunResult] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(RunResult.model_validate(json.loads(line)))

    tokens_total = sum(row.tokens_total for row in rows)
    latency_ms_total = sum(row.latency_ms_total for row in rows)
    llm_calls = sum(row.llm_calls for row in rows)
    estimated_usd = 0.0
    price_known = True
    for row in rows:
        if row.tokens_total <= 0:
            continue
        prices = price_table.get(row.model_id, {})
        if not prices:
            price_known = False
        estimated_usd += _row_cost_usd(row.tokens_total, prices)

    return {
        "run_path": str(path),
        "n": len(rows),
        "tokens_total": tokens_total,
        "latency_ms_total": latency_ms_total,
        "llm_calls": llm_calls,
        "estimated_usd": round(estimated_usd, 6),
        "price_known": price_known,
    }

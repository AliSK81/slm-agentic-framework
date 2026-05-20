#!/usr/bin/env python3
"""Populate humaneval_discriminative_deepseek in cite_allowlist.yaml from valid traces."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval.curated import DEEPSEEK_DISCRIMINATIVE_SECTION, EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS
from eval.run_quality import assess_run

TRACES = _PROJECT_ROOT / "traces"
ALLOWLIST = _PROJECT_ROOT / "configs" / "cite_allowlist.yaml"
CONFIGS = ("A", "B", "C", "D")
SEEDS = (41, 42, 43)


def _best_valid_runs() -> dict[tuple[str, int], dict[str, object]]:
    """Pick latest quality-valid n=30 discriminative run per (config, seed)."""
    best: dict[tuple[str, int], tuple[str, dict[str, object]]] = {}
    for manifest_path in TRACES.glob("*_discriminative_*.manifest.json"):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        config = str(payload.get("config", ""))
        seed = int(payload.get("seed", -1))
        n = int(payload.get("n", 0))
        if config not in CONFIGS or seed not in SEEDS or n != 30:
            continue
        run_id = manifest_path.name.replace(".manifest.json", "")
        trace_path = TRACES / f"{run_id}.jsonl"
        if not trace_path.is_file():
            continue
        quality = assess_run(str(trace_path))
        if not quality.valid:
            continue
        key = (config, seed)
        if key not in best or run_id > best[key][0]:
            best[key] = (run_id, payload)
    return {key: {"run_id": rid, **data} for key, (rid, data) in best.items()}


def main() -> int:
    """Update allowlist section; exit 1 if fewer than 12 valid runs."""
    runs_map = _best_valid_runs()
    entries = []
    for config in CONFIGS:
        for seed in SEEDS:
            key = (config, seed)
            if key not in runs_map:
                print(f"missing valid run: config={config} seed={seed}", file=sys.stderr)
                continue
            row = runs_map[key]
            entries.append(
                {
                    "run_id": row["run_id"],
                    "seed": seed,
                    "config": config,
                    "dataset": "discriminative",
                    "quality_valid": True,
                    "note": f"Phase-31 DeepSeek discriminative n=30 seed={seed}",
                }
            )

    if len(entries) < EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS:
        print(
            f"only {len(entries)}/{EXPECTED_DEEPSEEK_DISCRIMINATIVE_RUNS} valid runs; "
            "finish ablation first",
            file=sys.stderr,
        )
        return 1

    raw = yaml.safe_load(ALLOWLIST.read_text(encoding="utf-8")) or {}
    sections = raw.get("sections") or {}
    sections[DEEPSEEK_DISCRIMINATIVE_SECTION] = entries
    raw["sections"] = sections
    ALLOWLIST.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    print(f"updated {DEEPSEEK_DISCRIMINATIVE_SECTION} with {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

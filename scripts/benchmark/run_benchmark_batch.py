#!/usr/bin/env python3
"""Run a fixed batch of HumanEval tasks (e.g. prior 3 + extra sample)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from eval.config import load_eval_config
from eval.datasets._sample import sample_items
from eval.datasets.humaneval_adapter import load_humaneval, task_to_session
from eval.metrics import RunResult, compute_cer, compute_sr
from eval.run_eval import _run_single_task, _traces_dir

PRIOR_THREE = ("HumanEval/131", "HumanEval/28", "HumanEval/1")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run HumanEval benchmark batch")
    parser.add_argument("--config", default="D")
    parser.add_argument("--extra", type=int, default=7, help="Additional tasks beyond prior 3")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from framework.env import load_project_env

    load_project_env()

    all_by_id = {t.task_id: t for t in load_humaneval(n=164, seed=args.seed)}
    missing = [tid for tid in PRIOR_THREE if tid not in all_by_id]
    if missing:
        print("Missing task ids:", missing, file=sys.stderr)
        return 1

    pool = [t for tid, t in all_by_id.items() if tid not in PRIOR_THREE]
    extra = sample_items(pool, args.extra, args.seed)
    selected = [all_by_id[tid] for tid in PRIOR_THREE] + extra

    eval_config = load_eval_config()
    budget = eval_config.step_budgets.get("humaneval")
    max_steps = budget.max_steps if budget else 10
    max_retries = budget.max_retries if budget else 3
    flags = eval_config.ablation_configs[args.config]

    traces_root = _traces_dir()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jsonl_path = traces_root / f"{args.config}_humaneval_batch_{timestamp}.jsonl"

    results: list[RunResult] = []
    print(f"Running {len(selected)} tasks (config {args.config})...")
    for task in selected:
        goal, constraints, test_code = task_to_session(task)
        print(f"  -> {task.task_id}", flush=True)
        row = _run_single_task(
            task.task_id,
            goal,
            constraints,
            test_code,
            config_name=args.config,
            dataset_name="humaneval",
            flags=flags,
            max_steps=max_steps,
            max_retries=max_retries,
            traces_root=traces_root,
            dry_run=False,
        )
        results.append(row)
        status = "PASS" if row.solved else row.outcome
        print(f"     {status} (decisions={row.interaction_count}, steps={row.step_count})")

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row.model_dump(), default=str) + "\n")

    summary = {
        "sr": compute_sr(results),
        "cer": compute_cer(results),
        "n": len(results),
        "config": args.config,
        "trace_file": str(jsonl_path),
        "task_ids": [r.task_id for r in results],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

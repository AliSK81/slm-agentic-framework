"""Interaction-length sweep for RQ3 (CER vs required interaction steps)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from eval.config import load_eval_config
from eval.datasets.synthetic_multistep import (
    generate_multistep,
    multistep_to_session,
)
from eval.manifest import manifest_provider_and_profiles, resolve_git_sha, write_manifest
from eval.metrics import RunResult, compute_cer, compute_sr
from eval.run_eval import ConfigName, _run_single_task, _traces_dir

logger = logging.getLogger(__name__)

_DATASET_NAME = "multistep"


def _parse_levels(raw: str) -> list[int]:
    """Parse comma-separated level list (e.g. ``2,4,6,8``)."""
    levels = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not levels:
        raise ValueError("At least one interaction level is required")
    return levels


def run_interaction_length(
    config: str,
    levels: list[int],
    seed: int = 42,
    *,
    per_level: int = 5,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run config on L-step synthetic tasks for each level; write JSONL per level.

    Inputs:
        config: Ablation config name (``A``–``D``).
        levels: Required interaction lengths L to sweep.
        seed: Task generation and sampling seed.
        per_level: Synthetic tasks per level.
        dry_run: Build tasks and traces without calling the SLM API.

    Outputs:
        Dict keyed by level string with SR, CER, mean_interactions, and trace paths.

    Side effects:
        Writes aggregate JSONL and manifest under ``traces/`` per level.
    """
    config_name: ConfigName = config  # type: ignore[assignment]
    eval_config = load_eval_config()
    if config_name not in eval_config.ablation_configs:
        raise ValueError(f"Unknown config: {config_name}")

    flags = eval_config.ablation_configs[config_name]
    budget = eval_config.step_budgets.get(
        "multistep",
        eval_config.step_budgets.get("humaneval"),
    )
    max_steps = budget.max_steps if budget else 15
    max_retries = budget.max_retries if budget else 3

    all_tasks = generate_multistep(levels=levels, per_level=per_level, seed=seed)
    traces_root = _traces_dir()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    provider, planner_profile, executor_profile = manifest_provider_and_profiles()

    by_level: dict[str, dict[str, Any]] = {}

    for level in levels:
        level_tasks = [task for task in all_tasks if task.required_steps == level]
        run_id = f"{config_name}_multistep_L{level}_{timestamp}"
        jsonl_path = traces_root / f"{run_id}.jsonl"

        results: list[RunResult] = []
        for task in level_tasks:
            goal, constraints, test_code = multistep_to_session(task)
            logger.info("Interaction-length L=%s task %s", level, task.task_id)
            try:
                row = _run_single_task(
                    task.task_id,
                    goal,
                    constraints,
                    test_code,
                    config_name=config_name,
                    dataset_name=_DATASET_NAME,
                    flags=flags,
                    max_steps=max_steps,
                    max_retries=max_retries,
                    traces_root=traces_root,
                    dry_run=dry_run,
                    solution_stub=task.reference_solution if dry_run else None,
                )
            except Exception as exc:  # noqa: BLE001 — continue across tasks
                logger.exception("Task %s failed: %s", task.task_id, exc)
                row = RunResult(
                    task_id=task.task_id,
                    solved=False,
                    outcome="unresolvable",
                    interaction_count=0,
                )
            results.append(row)

        with jsonl_path.open("w", encoding="utf-8") as handle:
            for row in results:
                handle.write(json.dumps(row.model_dump(), default=str) + "\n")

        mean_ix = (
            sum(row.interaction_count for row in results) / len(results)
            if results
            else 0.0
        )
        manifest_path = write_manifest(
            run_id,
            traces_dir=traces_root,
            config=config_name,
            dataset=_DATASET_NAME,
            n=len(results),
            seed=seed,
            provider=provider,
            planner_profile=planner_profile,
            executor_profile=executor_profile,
            git_sha=resolve_git_sha(_PROJECT_ROOT),
            task_ids=[task.task_id for task in level_tasks],
            ablation_flags=flags.model_dump(),
            created_at=datetime.now(UTC),
        )

        by_level[str(level)] = {
            "sr": compute_sr(results),
            "cer": compute_cer(results),
            "mean_interactions": mean_ix,
            "n": len(results),
            "trace_file": str(jsonl_path),
            "manifest_file": str(manifest_path),
        }

    summary = {
        "config": config_name,
        "seed": seed,
        "per_level": per_level,
        "levels": by_level,
        "timestamp": timestamp,
        "dry_run": dry_run,
    }
    logger.info("Interaction-length sweep complete: %s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m eval.scenarios.interaction_length --config D --levels 2,4,6,8 --dry-run``."""
    parser = argparse.ArgumentParser(
        description="RQ3 interaction-length sweep on synthetic multi-step tasks",
    )
    parser.add_argument("--config", required=True, choices=["A", "B", "C", "D"])
    parser.add_argument(
        "--levels",
        default="2,4,6,8",
        help="Comma-separated required step counts (default: 2,4,6,8)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--per-level", type=int, default=5)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build tasks and write traces without calling the SLM API",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    summary = run_interaction_length(
        args.config,
        _parse_levels(args.levels),
        seed=args.seed,
        per_level=args.per_level,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

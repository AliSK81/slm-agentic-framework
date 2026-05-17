"""Evaluation CLI — run one config on one dataset and write JSONL traces."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from eval.config import AblationFlags, EvalConfig, load_eval_config
from eval.datasets.humaneval_adapter import load_humaneval, task_to_session
from eval.datasets.mbpp_adapter import load_mbpp, task_to_session as mbpp_task_to_session
from eval.datasets.swebench_adapter import load_swebench
from eval.metrics import RunResult, compute_cer, compute_sr
from eval.paths import safe_task_slug

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"

DatasetName = Literal["humaneval", "mbpp", "swebench"]
ConfigName = Literal["A", "B", "C", "D"]


def _ensure_import_paths() -> None:
    """Allow imports from ``src/framework`` when invoked as a script."""
    src = str(_SRC_ROOT)
    if src not in sys.path:
        sys.path.insert(0, src)


def _traces_dir() -> Path:
    path = _PROJECT_ROOT / "traces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_tasks(
    dataset_name: DatasetName,
    n: int,
    seed: int,
    eval_config: EvalConfig | None = None,
) -> list[tuple[str, str, list[str], str]]:
    """Return list of (task_id, goal, constraints, test_code)."""
    if dataset_name == "humaneval":
        split = None
        if eval_config is not None:
            raw_split = eval_config.humaneval.get("difficulty_split")
            if isinstance(raw_split, dict):
                split = {str(k): int(v) for k, v in raw_split.items()}
        return [
            (task.task_id, *task_to_session(task))
            for task in load_humaneval(n=n, seed=seed, difficulty_split=split)
        ]
    if dataset_name == "mbpp":
        return [
            (task.task_id, *mbpp_task_to_session(task))
            for task in load_mbpp(n=n, seed=seed)
        ]
    if dataset_name == "swebench":
        tasks = load_swebench(n=n, seed=seed)
        rows: list[tuple[str, str, list[str], str]] = []
        for task in tasks:
            goal = f"Fix the issue in {task.repo} @ {task.base_commit}:\n\n{task.problem_statement}"
            constraints = ["SWE-bench execution requires Docker (not run in Phase 10 harness)"]
            rows.append((task.task_id, goal, constraints, "assert False  # placeholder"))
        return rows
    raise ValueError(f"Unknown dataset: {dataset_name}")


def _run_single_task(
    task_id: str,
    goal: str,
    constraints: list[str],
    test_code: str,
    *,
    config_name: str,
    dataset_name: str,
    flags: AblationFlags,
    max_steps: int,
    max_retries: int,
    traces_root: Path,
    dry_run: bool,
    planner_enabled: bool = True,
) -> RunResult:
    """Execute one task and return a typed result row."""
    slug = safe_task_slug(task_id)
    workspace = traces_root / "workspaces" / config_name / dataset_name / slug
    trace_path = traces_root / "per_task" / config_name / dataset_name / f"{slug}.json"

    if dry_run:
        return RunResult(
            task_id=task_id,
            solved=False,
            outcome="dry_run",
            interaction_count=0,
            step_count=0,
            retry_count=0,
            trace_path=str(trace_path),
        )

    _ensure_import_paths()
    from framework.env import load_project_env
    from framework.control.ablation import AblationSettings
    from framework.orchestration.session import run_full_session

    load_project_env()
    workspace.mkdir(parents=True, exist_ok=True)
    ablation = AblationSettings(**flags.model_dump())
    session = run_full_session(
        goal,
        constraints,
        test_code,
        workspace,
        max_steps=max_steps,
        max_retries=max_retries,
        checkpoint_dir=traces_root / "checkpoints",
        ablation=ablation,
        planner_enabled=planner_enabled,
    )
    solved = session.test_passed and session.outcome == "solved"
    row = RunResult(
        task_id=task_id,
        solved=solved,
        outcome=session.outcome,
        interaction_count=session.decision_count,
        step_count=session.step_count,
        retry_count=session.retry_count,
        trace_path=str(trace_path),
    )
    try:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(row.model_dump(), default=str) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not write per-task trace %s: %s", trace_path, exc)
    return row


def run_eval(
    config_name: ConfigName,
    dataset_name: DatasetName,
    n: int | None = None,
    seed: int = 42,
    *,
    dry_run: bool = False,
    planner_enabled: bool = True,
) -> dict[str, Any]:
    """Run evaluation for one ablation config on one dataset.

    Writes aggregate JSONL to ``traces/{config}_{dataset}_{timestamp}.jsonl``.
    Returns summary dict with SR, CER, and task count.
    """
    eval_config: EvalConfig = load_eval_config()
    if config_name not in eval_config.ablation_configs:
        raise ValueError(f"Unknown config: {config_name}")

    dataset_block = getattr(eval_config, dataset_name, {})
    sample_n = n if n is not None else int(dataset_block.get("sample_size", 50))
    sample_seed = int(dataset_block.get("seed", seed))
    budget = eval_config.step_budgets.get(
        dataset_name,
        eval_config.step_budgets.get("humaneval"),
    )
    max_steps = budget.max_steps if budget else 10
    max_retries = budget.max_retries if budget else 3
    flags = eval_config.ablation_configs[config_name]

    tasks = _load_tasks(dataset_name, sample_n, sample_seed, eval_config)
    traces_root = _traces_dir()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    jsonl_path = traces_root / f"{config_name}_{dataset_name}_{timestamp}.jsonl"

    results: list[RunResult] = []
    for task_id, goal, constraints, test_code in tasks:
        logger.info("Evaluating %s / %s", dataset_name, task_id)
        try:
            row = _run_single_task(
                task_id,
                goal,
                constraints,
                test_code,
                config_name=config_name,
                dataset_name=dataset_name,
                flags=flags,
                max_steps=max_steps,
                max_retries=max_retries,
                traces_root=traces_root,
                dry_run=dry_run,
                planner_enabled=planner_enabled,
            )
        except Exception as exc:  # noqa: BLE001 — eval must continue across tasks
            logger.exception("Task %s failed: %s", task_id, exc)
            slug = safe_task_slug(task_id)
            row = RunResult(
                task_id=task_id,
                solved=False,
                outcome="unresolvable",
                interaction_count=0,
                trace_path=str(
                    traces_root
                    / "per_task"
                    / config_name
                    / dataset_name
                    / f"{slug}.json"
                ),
            )
        results.append(row)

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row.model_dump(), default=str) + "\n")

    summary: dict[str, Any] = {
        "sr": compute_sr(results),
        "cer": compute_cer(results),
        "n": len(results),
        "config": config_name,
    }
    summary["trace_file"] = str(jsonl_path)
    summary["dataset"] = dataset_name
    logger.info("Eval complete: %s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python -m eval.run_eval D humaneval --n 5 --dry-run``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run SLM agent evaluation harness")
    parser.add_argument("config", choices=["A", "B", "C", "D"])
    parser.add_argument("dataset", choices=["humaneval", "mbpp", "swebench"])
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    summary = run_eval(
        args.config,
        args.dataset,
        n=args.n,
        seed=args.seed,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

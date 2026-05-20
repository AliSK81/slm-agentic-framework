"""Evaluation CLI — run one config on one dataset and write JSONL traces."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from eval.config import AblationFlags, EvalConfig, load_eval_config
from eval.datasets.humaneval_adapter import (
    load_humaneval,
    load_humaneval_by_ids,
    load_humaneval_curated_hard,
    task_solution_stub,
    task_to_session,
)
from eval.datasets.mbpp_adapter import (
    load_mbpp,
    load_mbpp_by_ids,
    task_to_session as mbpp_task_to_session,
)
from eval.datasets.synthetic_multistep import generate_multistep, multistep_to_session
from eval.datasets.swebench_adapter import (
    SWEBenchTask,
    load_swebench,
    load_swebench_by_ids,
    materialize_instance_workspace,
    task_to_session as swebench_task_to_session,
)
from eval.swe_docker import DockerNotAvailableError, require_docker, run_swe_instance_tests
from eval.manifest import manifest_provider_and_profiles, resolve_git_sha, write_manifest
from eval.metrics import RunResult, compute_cer, compute_sr
from eval.paths import safe_task_slug
from eval.run_quality import assess_run

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"

DatasetName = Literal["humaneval", "humaneval_hard", "multistep", "mbpp", "swebench"]
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
    *,
    dry_run: bool = False,
) -> list[tuple[str, str, list[str], str, str | None]]:
    """Return list of (task_id, goal, constraints, test_code, solution_stub)."""
    if dataset_name == "multistep":
        block = eval_config.multistep if eval_config is not None else {}
        levels = [int(value) for value in block.get("levels", [2, 4, 6, 8])]
        per_level = int(block.get("per_level", 5))
        generated = generate_multistep(levels=levels, per_level=per_level, seed=seed)
        if n < len(generated):
            from eval.datasets._sample import sample_items

            generated = sample_items(generated, n, seed)
        return [
            (
                task.task_id,
                *multistep_to_session(task),
                task.reference_solution,
            )
            for task in generated
        ]
    if dataset_name == "humaneval_hard":
        block = eval_config.humaneval_hard if eval_config is not None else {}
        if block.get("curated_only", True):
            tasks = load_humaneval_curated_hard(n=n, seed=seed)
        else:
            difficulty = str(block.get("difficulty", "hard"))
            tasks = load_humaneval(n=n, seed=seed, difficulty=difficulty)
        return [
            (task.task_id, *task_to_session(task), task_solution_stub(task))
            for task in tasks
        ]
    if dataset_name == "humaneval":
        split = None
        if eval_config is not None:
            raw_split = eval_config.humaneval.get("difficulty_split")
            if isinstance(raw_split, dict):
                split = {str(k): int(v) for k, v in raw_split.items()}
        return [
            (task.task_id, *task_to_session(task), task_solution_stub(task))
            for task in load_humaneval(n=n, seed=seed, difficulty_split=split)
        ]
    if dataset_name == "mbpp":
        return [
            (task.task_id, *mbpp_task_to_session(task), None)
            for task in load_mbpp(n=n, seed=seed)
        ]
    if dataset_name == "swebench":
        block = eval_config.swebench if eval_config is not None else {}
        docker_required = bool(block.get("docker_required", True)) and not dry_run
        return [
            (task.task_id, *swebench_task_to_session(task), None)
            for task in load_swebench(n=n, seed=seed, docker_required=docker_required)
        ]
    raise ValueError(f"Unknown dataset: {dataset_name}")


def _load_tasks_by_ids(
    dataset_name: DatasetName,
    task_ids: list[str],
) -> list[tuple[str, str, list[str], str, str | None]]:
    """Load exactly the named tasks (no sampling)."""
    if dataset_name in ("humaneval", "humaneval_hard"):
        return [
            (task.task_id, *task_to_session(task), task_solution_stub(task))
            for task in load_humaneval_by_ids(task_ids)
        ]
    if dataset_name == "mbpp":
        return [
            (task.task_id, *mbpp_task_to_session(task), None)
            for task in load_mbpp_by_ids(task_ids)
        ]
    if dataset_name == "swebench":
        return [
            (task.task_id, *swebench_task_to_session(task), None)
            for task in load_swebench_by_ids(task_ids)
        ]
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
    solution_stub: str | None = None,
    swe_task: SWEBenchTask | None = None,
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
    if solution_stub:
        stub_path = workspace / "solution.py"
        if not stub_path.is_file():
            stub_path.write_text(solution_stub, encoding="utf-8")
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
    if swe_task is not None:
        try:
            repo_dir = materialize_instance_workspace(swe_task, workspace)
            docker_result = run_swe_instance_tests(
                instance_id=swe_task.task_id,
                workspace=repo_dir,
                fail_to_pass=swe_task.fail_to_pass,
                pass_to_pass=swe_task.pass_to_pass,
            )
            solved = docker_result.passed
        except Exception as exc:  # noqa: BLE001 — materialize/docker must not crash eval
            logger.exception("SWE Docker grading failed for %s: %s", task_id, exc)
            solved = False
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
    task_ids: list[str] | None = None,
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

    if dataset_name == "swebench" and not dry_run:
        require_docker(bool(dataset_block.get("docker_required", True)))

    if task_ids:
        tasks = _load_tasks_by_ids(dataset_name, task_ids)
        sample_n = len(tasks)
    else:
        tasks = _load_tasks(
            dataset_name, sample_n, sample_seed, eval_config, dry_run=dry_run
        )

    swe_lookup: dict[str, SWEBenchTask] = {}
    if dataset_name == "swebench":
        swe_rows = (
            load_swebench_by_ids(task_ids)
            if task_ids
            else load_swebench(
                n=sample_n,
                seed=sample_seed,
                docker_required=False,
            )
        )
        swe_lookup = {row.task_id: row for row in swe_rows}

    traces_root = _traces_dir()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{config_name}_{dataset_name}_{timestamp}"
    jsonl_path = traces_root / f"{run_id}.jsonl"

    results: list[RunResult] = []
    for task_id, goal, constraints, test_code, solution_stub in tasks:
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
                solution_stub=solution_stub,
                swe_task=swe_lookup.get(task_id),
            )
        except DockerNotAvailableError:
            raise
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

    n_valid_tasks = sum(1 for row in results if row.interaction_count > 0)
    summary: dict[str, Any] = {
        "sr": compute_sr(results),
        "cer": compute_cer(results),
        "n": len(results),
        "n_valid_tasks": n_valid_tasks,
        "config": config_name,
        "seed": sample_seed,
    }
    summary["trace_file"] = str(jsonl_path)
    summary["dataset"] = dataset_name
    summary["run_id"] = run_id

    provider, planner_profile, executor_profile = manifest_provider_and_profiles()
    manifest_path = write_manifest(
        run_id,
        traces_dir=traces_root,
        config=config_name,
        dataset=dataset_name,
        n=sample_n,
        seed=sample_seed,
        provider=provider,
        planner_profile=planner_profile,
        executor_profile=executor_profile,
        git_sha=resolve_git_sha(_PROJECT_ROOT),
        task_ids=[task_id for task_id, *_ in tasks],
        ablation_flags=flags.model_dump(),
        created_at=datetime.now(UTC),
    )
    summary["manifest_file"] = str(manifest_path)

    if dry_run:
        summary["run_valid"] = True
        summary["run_invalid_reason"] = None
    elif not dry_run:
        quality = assess_run(str(jsonl_path))
        quality_path = jsonl_path.with_name(f"{jsonl_path.stem}.quality.json")
        quality_payload = {
            **quality.model_dump(),
            "run_valid": quality.valid,
            "run_invalid_reason": quality.reason,
        }
        quality_path.write_text(
            json.dumps(quality_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        summary["run_valid"] = quality.valid
        summary["run_invalid_reason"] = quality.reason
        summary["quality_file"] = str(quality_path)
        if not quality.valid:
            print(f"RUN INVALID: {quality.reason}", file=sys.stderr)

    logger.info("Eval complete: %s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python -m eval.run_eval --config D --dataset humaneval --dry-run``."""
    import argparse

    parser = argparse.ArgumentParser(description="Run SLM agent evaluation harness")
    parser.add_argument(
        "config",
        nargs="?",
        choices=["A", "B", "C", "D"],
        help="Ablation config (positional or use --config)",
    )
    parser.add_argument(
        "dataset",
        nargs="?",
        choices=["humaneval", "humaneval_hard", "mbpp", "swebench"],
        help="Dataset name (positional or use --dataset)",
    )
    parser.add_argument("--config", dest="config_flag", choices=["A", "B", "C", "D"])
    parser.add_argument(
        "--dataset",
        dest="dataset_flag",
        choices=["humaneval", "humaneval_hard", "mbpp", "swebench"],
    )
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--task-id",
        action="append",
        dest="task_ids",
        default=None,
        help="Run only these task IDs (repeatable); bypasses sampling",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    config_name = args.config_flag or args.config
    dataset_name = args.dataset_flag or args.dataset
    if not config_name or not dataset_name:
        parser.error("config and dataset are required (positional or --config/--dataset)")

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    summary = run_eval(
        config_name,
        dataset_name,
        n=args.n,
        seed=args.seed,
        task_ids=args.task_ids,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2))
    if summary.get("run_valid") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

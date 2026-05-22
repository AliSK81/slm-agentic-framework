"""Agent-count experiment: config D with one vs two agents (RQ3 CER focus)."""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from eval.config import load_eval_config
from eval.run_eval import DatasetName, run_eval

logger = logging.getLogger(__name__)

AgentCountDataset = DatasetName


class AgentCountArmResult(BaseModel):
    """Metrics for one agent-count arm (planner on or off)."""

    planner_enabled: bool
    sr: float
    cer: float
    n: int
    n_valid_tasks: int = 0
    mean_interactions: float = 0.0
    contradiction_count: int = 0
    trace_file: str = ""
    manifest_file: str = ""
    seeds: list[int] = Field(default_factory=list)


class AgentCountResult(BaseModel):
    """Comparison of two-agent vs one-agent runs on the same task sample."""

    dataset: str
    n_tasks: int
    seeds: list[int]
    two_agent: AgentCountArmResult
    one_agent: AgentCountArmResult
    timestamp: str


def _parse_seeds(raw: str | None, fallback: int) -> list[int]:
    if not raw:
        return [fallback]
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("At least one seed is required")
    return values


def _mean_interactions_from_trace(trace_file: str) -> float:
    """Compute mean interaction_count over tasks with at least one interaction."""
    path = Path(trace_file)
    if not path.is_file():
        return 0.0
    counts: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ix = int(row.get("interaction_count", 0))
        if ix > 0:
            counts.append(ix)
    return float(statistics.mean(counts)) if counts else 0.0


def _contradiction_count_from_trace(trace_file: str) -> int:
    """Count contradictions via decision JSONL when manifest is present."""
    from scripts.reporting.analyze_traces import count_contradictions

    return count_contradictions(trace_file)


def _aggregate_arm(
    summaries: list[dict[str, object]],
    *,
    planner_enabled: bool,
    seeds: list[int],
) -> AgentCountArmResult:
    """Aggregate per-seed run_eval summaries into one arm result."""
    if not summaries:
        return AgentCountArmResult(planner_enabled=planner_enabled, sr=0.0, cer=0.0, n=0)

    sr_values = [float(s["sr"]) for s in summaries]
    cer_values = [float(s["cer"]) for s in summaries]
    mean_ix_values = [
        _mean_interactions_from_trace(str(s.get("trace_file", ""))) for s in summaries
    ]
    contradictions = sum(
        _contradiction_count_from_trace(str(s.get("trace_file", ""))) for s in summaries
    )
    last = summaries[-1]
    return AgentCountArmResult(
        planner_enabled=planner_enabled,
        sr=float(statistics.mean(sr_values)),
        cer=float(statistics.mean(cer_values)),
        n=int(last.get("n", 0)),
        n_valid_tasks=int(
            statistics.mean(int(s.get("n_valid_tasks", 0)) for s in summaries)
        ),
        mean_interactions=float(statistics.mean(mean_ix_values)) if mean_ix_values else 0.0,
        contradiction_count=contradictions,
        trace_file=str(last.get("trace_file", "")),
        manifest_file=str(last.get("manifest_file", "")),
        seeds=seeds,
    )


def run_agent_count_experiment(
    dataset: AgentCountDataset = "multistep",
    n: int | None = None,
    seed: int = 42,
    *,
    seeds: list[int] | None = None,
    dry_run: bool = False,
) -> AgentCountResult:
    """Run config D with planner+executor vs executor-only on the same tasks.

    Inputs: dataset name, sample size, seed list, dry_run flag.
    Outputs: :class:`AgentCountResult` with SR, CER, mean interactions per arm.
    Side effects: writes manifested JSONL traces via :func:`run_eval`.
    """
    seed_list = seeds if seeds is not None else [seed]
    eval_config = load_eval_config()
    block = getattr(eval_config, dataset, {})
    sample_n = n if n is not None else int(block.get("sample_size", 30))

    logger.info(
        "Agent-count experiment on %s (n=%s, seeds=%s)",
        dataset,
        sample_n,
        seed_list,
    )

    two_summaries: list[dict[str, object]] = []
    one_summaries: list[dict[str, object]] = []

    for run_seed in seed_list:
        two_summaries.append(
            run_eval(
                "D",
                dataset,
                n=sample_n,
                seed=run_seed,
                dry_run=dry_run,
                planner_enabled=True,
            )
        )
        one_summaries.append(
            run_eval(
                "D",
                dataset,
                n=sample_n,
                seed=run_seed,
                dry_run=dry_run,
                planner_enabled=False,
            )
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result = AgentCountResult(
        dataset=dataset,
        n_tasks=sample_n,
        seeds=seed_list,
        two_agent=_aggregate_arm(two_summaries, planner_enabled=True, seeds=seed_list),
        one_agent=_aggregate_arm(one_summaries, planner_enabled=False, seeds=seed_list),
        timestamp=timestamp,
    )
    _print_comparison(result)
    return result


def _print_comparison(result: AgentCountResult) -> None:
    """Print SR, CER, and mean interactions for both arms."""
    print("Agent-count comparison (config D):")
    for label, arm in (
        ("2 agents (planner+executor)", result.two_agent),
        ("1 agent  (executor-only)", result.one_agent),
    ):
        print(
            f"  {label} — SR {arm.sr:.1f}%  CER {arm.cer:.1f}%  "
            f"mean_ix {arm.mean_interactions:.2f}  "
            f"contradictions {arm.contradiction_count}  "
            f"trace: {arm.trace_file}"
        )
    print(f"Dataset: {result.dataset}  n={result.n_tasks}  seeds={result.seeds}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry for agent-count experiment."""
    parser = argparse.ArgumentParser(description="Agent-count ablation (config D)")
    parser.add_argument(
        "dataset",
        nargs="?",
        default="multistep",
        choices=["humaneval", "humaneval_hard", "multistep", "mbpp", "swebench"],
    )
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--seeds",
        default=None,
        help="Comma-separated seeds (overrides --seed)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    result = run_agent_count_experiment(
        args.dataset,  # type: ignore[arg-type]
        n=args.n,
        seed=args.seed,
        seeds=_parse_seeds(args.seeds, args.seed),
        dry_run=args.dry_run,
    )
    print(json.dumps(result.model_dump(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

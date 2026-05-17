"""Agent-count experiment: config D with one vs two agents."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from eval.run_eval import DatasetName, run_eval

logger = logging.getLogger(__name__)


def run_agent_count_experiment(
    dataset: str = "swebench",
    n: int = 30,
    seed: int = 42,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run config D with two agents (planner+executor) vs executor-only.

    Returns:
        Dict with ``two_agent`` and ``one_agent`` summaries (SR, CER, trace_file).
    """
    dataset_name: DatasetName = dataset  # type: ignore[assignment]
    logger.info("Agent-count experiment on %s (n=%s)", dataset, n)

    two_agent = run_eval(
        "D",
        dataset_name,
        n=n,
        seed=seed,
        dry_run=dry_run,
        planner_enabled=True,
    )
    one_agent = run_eval(
        "D",
        dataset_name,
        n=n,
        seed=seed,
        dry_run=dry_run,
        planner_enabled=False,
    )

    result = {
        "dataset": dataset,
        "n": n,
        "seed": seed,
        "two_agent": two_agent,
        "one_agent": one_agent,
    }
    print("Agent-count comparison (config D):")
    print(
        f"  2 agents — SR {two_agent['sr']:.1f}%  CER {two_agent['cer']:.1f}%  "
        f"trace: {two_agent.get('trace_file', '')}"
    )
    print(
        f"  1 agent  — SR {one_agent['sr']:.1f}%  CER {one_agent['cer']:.1f}%  "
        f"trace: {one_agent.get('trace_file', '')}"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry for agent-count experiment."""
    parser = argparse.ArgumentParser(description="Agent-count ablation (config D)")
    parser.add_argument(
        "dataset",
        nargs="?",
        default="swebench",
        choices=["humaneval", "mbpp", "swebench"],
    )
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    result = run_agent_count_experiment(
        args.dataset,
        n=args.n,
        seed=args.seed,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

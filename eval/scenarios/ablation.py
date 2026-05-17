"""Run ablation configs A–D on the same task sample and print a comparison table."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pydantic import BaseModel, Field

from eval.config import AblationFlags, load_eval_config
from eval.run_eval import ConfigName, DatasetName, run_eval

logger = logging.getLogger(__name__)

CONFIG_ORDER: tuple[ConfigName, ...] = ("A", "B", "C", "D")


class ConfigResult(BaseModel):
    """SR/CER and trace path for one ablation config."""

    sr: float
    cer: float
    n: int
    trace_file: str = ""


class AblationResult(BaseModel):
    """Aggregate ablation run across configs A–D."""

    dataset: str
    n_tasks: int
    seed: int
    configs: dict[str, ConfigResult] = Field(default_factory=dict)
    timestamp: str


def _yn(value: bool) -> str:
    return "Yes" if value else "No"


def print_comparison_table(
    result: AblationResult,
    flags_by_config: dict[str, AblationFlags] | None = None,
) -> None:
    """Print SR/CER table with feature columns for each config."""
    flags_by_config = flags_by_config or {}
    header = (
        f"{'Config':<8} {'SR (%)':>8} {'CER (%)':>9} "
        f"{'Memory':<8} {'Control':<9} {'Error Ctrl':<10}"
    )
    print(header)
    print("-" * len(header))
    for name in CONFIG_ORDER:
        row = result.configs.get(name)
        if row is None:
            continue
        flags = flags_by_config.get(name, AblationFlags())
        print(
            f"{name:<8} {row.sr:>8.1f} {row.cer:>9.1f} "
            f"{_yn(flags.memory):<8} {_yn(flags.control):<9} {_yn(flags.error_control):<10}"
        )
    print(f"\nDataset: {result.dataset}  n={result.n_tasks}  seed={result.seed}")
    print(f"Timestamp: {result.timestamp}")


def run_ablation(
    dataset: str,
    n: int = 50,
    seed: int = 42,
    *,
    dry_run: bool = False,
) -> AblationResult:
    """Run configs A–D on the same sample; write per-config JSONL traces.

    Returns:
        AblationResult with SR and CER per config.
    """
    dataset_name: DatasetName = dataset  # type: ignore[assignment]
    eval_config = load_eval_config()
    flags_map = eval_config.ablation_configs
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    config_results: dict[str, ConfigResult] = {}

    for config_name in CONFIG_ORDER:
        logger.info("Ablation config %s on %s (n=%s)", config_name, dataset, n)
        summary = run_eval(
            config_name,
            dataset_name,
            n=n,
            seed=seed,
            dry_run=dry_run,
        )
        config_results[config_name] = ConfigResult(
            sr=float(summary["sr"]),
            cer=float(summary["cer"]),
            n=int(summary["n"]),
            trace_file=str(summary.get("trace_file", "")),
        )

    result = AblationResult(
        dataset=dataset,
        n_tasks=n,
        seed=seed,
        configs=config_results,
        timestamp=timestamp,
    )
    print_comparison_table(result, flags_map)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python eval/scenarios/ablation.py humaneval --dry-run``."""
    parser = argparse.ArgumentParser(description="Run ablation configs A–D")
    parser.add_argument(
        "dataset",
        nargs="?",
        default="humaneval",
        choices=["humaneval", "mbpp", "swebench"],
    )
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    run_ablation(args.dataset, n=args.n, seed=args.seed, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

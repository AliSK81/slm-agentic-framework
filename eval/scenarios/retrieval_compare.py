"""Compare keyword vs semantic retrieval on memory configs B and D (RQ1)."""

from __future__ import annotations

import argparse
import logging
import os
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

from eval.config import load_eval_config
from eval.run_eval import run_eval
from eval.scenarios.ablation import _apply_profile_bundle, _apply_retrieval_mode

logger = logging.getLogger(__name__)

MEMORY_CONFIGS: tuple[str, ...] = ("B", "D")
RETRIEVAL_MODES: tuple[str, ...] = ("keyword", "semantic")


class ModeConfigResult(BaseModel):
    """Aggregated metrics for one config under one retrieval mode."""

    config: str
    sr: float
    cer: float
    n: int
    trace_file: str = ""


class RetrievalCompareResult(BaseModel):
    """Keyword vs semantic comparison on configs B and D."""

    dataset: str
    n_tasks: int
    seeds: list[int] = Field(default_factory=list)
    modes: dict[str, dict[str, ModeConfigResult]] = Field(default_factory=dict)
    timestamp: str = ""


def run_retrieval_compare(
    dataset: str,
    n: int = 30,
    seed: int = 42,
    *,
    seeds: list[int] | None = None,
    dry_run: bool = False,
    profile_bundle: str | None = None,
) -> RetrievalCompareResult:
    """Run B and D under keyword and semantic retrieval modes.

    Side effects:
        Sets ``MEMORY_RETRIEVAL_MODE`` per mode; writes traces via :func:`run_eval`.
    """
    _apply_profile_bundle(profile_bundle)
    seed_list = seeds if seeds is not None else [seed]
    modes_out: dict[str, dict[str, ModeConfigResult]] = {}
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    for mode in RETRIEVAL_MODES:
        _apply_retrieval_mode(mode)
        modes_out[mode] = {}
        for config_name in MEMORY_CONFIGS:
            srs: list[float] = []
            cers: list[float] = []
            last_trace = ""
            last_n = n
            for run_seed in seed_list:
                logger.info(
                    "Retrieval %s config %s dataset %s seed %s",
                    mode,
                    config_name,
                    dataset,
                    run_seed,
                )
                summary = run_eval(
                    config_name,  # type: ignore[arg-type]
                    dataset,  # type: ignore[arg-type]
                    n=n,
                    seed=run_seed,
                    dry_run=dry_run,
                )
                srs.append(float(summary["sr"]))
                cers.append(float(summary["cer"]))
                last_n = int(summary["n"])
                last_trace = str(summary.get("trace_file", ""))
            modes_out[mode][config_name] = ModeConfigResult(
                config=config_name,
                sr=sum(srs) / len(srs) if srs else 0.0,
                cer=sum(cers) / len(cers) if cers else 0.0,
                n=last_n,
                trace_file=last_trace,
            )

    return RetrievalCompareResult(
        dataset=dataset,
        n_tasks=n,
        seeds=seed_list,
        modes=modes_out,
        timestamp=timestamp,
    )


def print_retrieval_table(result: RetrievalCompareResult) -> None:
    """Print SR/CER for B and D under each retrieval mode."""
    header = (
        f"{'Mode':<10} {'Config':<8} {'SR mean':>8} {'CER mean':>9} "
        f"{'n':>4} {'Memory':<8} {'Retrieval':<10}"
    )
    print(header)
    print("-" * len(header))
    for mode in RETRIEVAL_MODES:
        for config_name in MEMORY_CONFIGS:
            row = result.modes.get(mode, {}).get(config_name)
            if row is None:
                continue
            print(
                f"{mode:<10} {config_name:<8} {row.sr:>8.1f} {row.cer:>9.1f} "
                f"{row.n:>4} {'Yes':<8} {mode:<10}"
            )
    seeds = ",".join(str(value) for value in result.seeds)
    retrieval_label = os.getenv("MEMORY_RETRIEVAL_MODE", "keyword")
    print(
        f"\nDataset: {result.dataset}  n={result.n_tasks}  seeds={seeds}  "
        f"last_retrieval={retrieval_label}"
    )
    print(f"Timestamp: {result.timestamp}")


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m eval.scenarios.retrieval_compare --dataset discriminative --dry-run``."""
    parser = argparse.ArgumentParser(description="Keyword vs semantic retrieval (B, D)")
    parser.add_argument("--dataset", default="discriminative")
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seeds", default=None, help="Comma-separated seeds")
    parser.add_argument("--profile-bundle", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    eval_config = load_eval_config()
    block = getattr(eval_config, args.dataset, {})
    sample_n = args.n if args.n is not None else int(block.get("sample_size", 30))
    seed_list = (
        [int(part.strip()) for part in args.seeds.split(",") if part.strip()]
        if args.seeds
        else [args.seed]
    )

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    result = run_retrieval_compare(
        args.dataset,
        n=sample_n,
        seeds=seed_list,
        dry_run=args.dry_run,
        profile_bundle=args.profile_bundle,
    )
    print_retrieval_table(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run ablation configs A–D on the same task sample and print a comparison table."""

from __future__ import annotations

import argparse
import logging
import os
import statistics
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

AblationDatasetName = DatasetName


class AblationRunInvalidError(RuntimeError):
    """Raised when a run fails the Phase-13 quality gate during ablation."""


class SeedRunResult(BaseModel):
    """Metrics for one (config, seed) eval run."""

    seed: int
    sr: float
    cer: float
    n: int
    n_valid_tasks: int
    trace_file: str = ""
    manifest_file: str = ""
    run_valid: bool = True
    run_invalid_reason: str | None = None


class ConfigResult(BaseModel):
    """Aggregated SR/CER across seeds for one ablation config."""

    sr: float
    cer: float
    sr_std: float = 0.0
    cer_std: float = 0.0
    n: int
    n_valid_tasks: int = 0
    trace_file: str = ""
    seeds: list[SeedRunResult] = Field(default_factory=list)


class AblationResult(BaseModel):
    """Aggregate ablation run across configs A–D."""

    dataset: str
    n_tasks: int
    seed: int
    seeds: list[int] = Field(default_factory=list)
    configs: dict[str, ConfigResult] = Field(default_factory=dict)
    timestamp: str


def _yn(value: bool) -> str:
    return "Yes" if value else "No"


def _parse_seeds(raw: str | None, fallback: int) -> list[int]:
    """Parse comma-separated seed list."""
    if not raw:
        return [fallback]
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("At least one seed is required")
    return values


def _apply_retrieval_mode(mode: str | None) -> None:
    """Set ``MEMORY_RETRIEVAL_MODE`` for keyword vs semantic retrieval (RQ1 axis)."""
    if not mode:
        return
    normalized = mode.strip().lower()
    if normalized not in ("keyword", "semantic"):
        raise ValueError(
            f"retrieval_mode must be 'keyword' or 'semantic', got {mode!r}"
        )
    os.environ["MEMORY_RETRIEVAL_MODE"] = normalized


def _apply_profile_bundle(bundle_name: str | None) -> None:
    """Apply optional SLM profile bundle or provider override (e.g. deepseek)."""
    if not bundle_name:
        return

    from framework.slm.config import _load_raw, clear_config_cache, resolve_bundle

    if bundle_name in (_load_raw().get("bundles") or {}):
        profiles = resolve_bundle(bundle_name)
        os.environ["PLANNER_PROFILE"] = profiles["planner"]
        os.environ["EXECUTOR_PROFILE"] = profiles["executor"]
        block = _load_raw().get("bundles", {}).get(bundle_name, {})
        provider = str(block.get("provider", "")).strip()
        if provider:
            os.environ["SLM_PROVIDER"] = provider
    elif bundle_name in (_load_raw().get("providers") or {}):
        os.environ["SLM_PROVIDER"] = bundle_name
        os.environ.pop("PLANNER_PROFILE", None)
        os.environ.pop("EXECUTOR_PROFILE", None)
        os.environ.pop("PLANNER_MODEL", None)
        os.environ.pop("EXECUTOR_MODEL", None)
    else:
        raise ValueError(
            f"Unknown profile bundle or provider {bundle_name!r}. "
            "Use a bundle from configs/models.yaml (e.g. slm_small) or a provider key (e.g. deepseek)."
        )
    clear_config_cache()


def _aggregate_seed_rows(rows: list[SeedRunResult]) -> ConfigResult:
    """Compute mean/std SR and CER across seed runs."""
    if not rows:
        return ConfigResult(sr=0.0, cer=0.0, n=0, n_valid_tasks=0)

    srs = [row.sr for row in rows]
    cers = [row.cer for row in rows]
    return ConfigResult(
        sr=statistics.mean(srs),
        cer=statistics.mean(cers),
        sr_std=statistics.pstdev(srs) if len(srs) > 1 else 0.0,
        cer_std=statistics.pstdev(cers) if len(cers) > 1 else 0.0,
        n=rows[0].n,
        n_valid_tasks=sum(row.n_valid_tasks for row in rows),
        trace_file=rows[-1].trace_file,
        seeds=rows,
    )


def print_comparison_table(
    result: AblationResult,
    flags_by_config: dict[str, AblationFlags] | None = None,
) -> None:
    """Print SR/CER table with validity and feature columns for each config."""
    flags_by_config = flags_by_config or {}
    header = (
        f"{'Config':<8} {'SR mean':>8} {'SR std':>7} {'CER mean':>9} {'CER std':>8} "
        f"{'n_valid':>8} {'Memory':<8} {'Control':<9} {'Error Ctrl':<10}"
    )
    print(header)
    print("-" * len(header))
    for name in CONFIG_ORDER:
        row = result.configs.get(name)
        if row is None:
            continue
        flags = flags_by_config.get(name, AblationFlags())
        print(
            f"{name:<8} {row.sr:>8.1f} {row.sr_std:>7.1f} {row.cer:>9.1f} {row.cer_std:>8.1f} "
            f"{row.n_valid_tasks:>8} "
            f"{_yn(flags.memory):<8} {_yn(flags.control):<9} {_yn(flags.error_control):<10}"
        )
    seed_label = ",".join(str(value) for value in result.seeds) or str(result.seed)
    retrieval_label = os.getenv("MEMORY_RETRIEVAL_MODE", "keyword")
    print(
        f"\nDataset: {result.dataset}  n={result.n_tasks}  seeds={seed_label}  "
        f"retrieval={retrieval_label}"
    )
    print(f"Timestamp: {result.timestamp}")


def run_ablation(
    dataset: str,
    n: int = 50,
    seed: int = 42,
    *,
    seeds: list[int] | None = None,
    dry_run: bool = False,
    profile_bundle: str | None = None,
    retrieval_mode: str | None = None,
) -> AblationResult:
    """Run configs A–D on the same sample across one or more seeds.

    Inputs:
        dataset: Dataset alias (``humaneval``, ``humaneval_hard``, ``multistep``, etc.).
        n: Task sample size per run.
        seed: Default seed when ``seeds`` is omitted.
        seeds: Optional list of seeds (e.g. ``[41, 42, 43]``).
        dry_run: Build manifests and traces without API calls.
        profile_bundle: Optional bundle (``slm_small``) or provider (``deepseek``).
        retrieval_mode: ``keyword`` or ``semantic`` — sets ``MEMORY_RETRIEVAL_MODE`` for RQ1.

    Outputs:
        AblationResult with per-config mean±std metrics.

    Side effects:
        Writes JSONL + manifest per (config, seed). Raises AblationRunInvalidError
        when any non-dry run fails the quality gate.
    """
    previous_retrieval_mode = os.environ.get("MEMORY_RETRIEVAL_MODE")
    try:
        _apply_profile_bundle(profile_bundle)
        _apply_retrieval_mode(retrieval_mode)
        dataset_name: AblationDatasetName = dataset  # type: ignore[assignment]
        eval_config = load_eval_config()
        flags_map = eval_config.ablation_configs
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        seed_list = seeds if seeds is not None else [seed]
        config_results: dict[str, ConfigResult] = {}

        for config_name in CONFIG_ORDER:
            per_seed: list[SeedRunResult] = []
            for run_seed in seed_list:
                logger.info(
                    "Ablation config %s on %s (n=%s, seed=%s)",
                    config_name,
                    dataset,
                    n,
                    run_seed,
                )
                summary = run_eval(
                    config_name,
                    dataset_name,
                    n=n,
                    seed=run_seed,
                    dry_run=dry_run,
                )
                run_valid = bool(summary.get("run_valid", True))
                if not dry_run and not run_valid:
                    reason = summary.get("run_invalid_reason", "unknown")
                    raise AblationRunInvalidError(
                        f"Run invalid for config {config_name} seed {run_seed} "
                        f"on {dataset}: {reason}"
                    )

                per_seed.append(
                    SeedRunResult(
                        seed=run_seed,
                        sr=float(summary["sr"]),
                        cer=float(summary["cer"]),
                        n=int(summary["n"]),
                        n_valid_tasks=int(summary.get("n_valid_tasks", summary["n"])),
                        trace_file=str(summary.get("trace_file", "")),
                        manifest_file=str(summary.get("manifest_file", "")),
                        run_valid=run_valid,
                        run_invalid_reason=summary.get("run_invalid_reason"),
                    )
                )

            config_results[config_name] = _aggregate_seed_rows(per_seed)

        result = AblationResult(
            dataset=dataset,
            n_tasks=n,
            seed=seed_list[0],
            seeds=seed_list,
            configs=config_results,
            timestamp=timestamp,
        )
        print_comparison_table(result, flags_map)
        return result
    finally:
        if previous_retrieval_mode is None:
            os.environ.pop("MEMORY_RETRIEVAL_MODE", None)
        else:
            os.environ["MEMORY_RETRIEVAL_MODE"] = previous_retrieval_mode


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m eval.scenarios.ablation --dataset humaneval_hard --seeds 41,42,43 --dry-run``."""
    parser = argparse.ArgumentParser(description="Run ablation configs A–D")
    parser.add_argument(
        "dataset",
        nargs="?",
        default=None,
        choices=[
            "humaneval",
            "humaneval_hard",
            "discriminative",
            "multistep",
            "mbpp",
            "swebench",
        ],
        help="Dataset (positional; optional if --dataset is set)",
    )
    parser.add_argument(
        "--dataset",
        dest="dataset_flag",
        choices=[
            "humaneval",
            "humaneval_hard",
            "discriminative",
            "multistep",
            "mbpp",
            "swebench",
        ],
    )
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--seeds",
        default=None,
        help="Comma-separated seeds (e.g. 41,42,43); overrides --seed when set",
    )
    parser.add_argument(
        "--profile-bundle",
        default=None,
        help="Profile bundle (slm_small) or provider key (deepseek); default uses models.yaml active_provider",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--retrieval-mode",
        choices=["keyword", "semantic"],
        default=None,
        help="Memory retrieval mechanism for configs with memory enabled (RQ1)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    dataset_name = args.dataset_flag or args.dataset or "humaneval"
    eval_config = load_eval_config()
    dataset_block = getattr(eval_config, dataset_name, {})
    sample_n = args.n if args.n is not None else int(dataset_block.get("sample_size", 50))

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    try:
        run_ablation(
            dataset_name,
            n=sample_n,
            seed=args.seed,
            seeds=_parse_seeds(args.seeds, args.seed),
            dry_run=args.dry_run,
            profile_bundle=args.profile_bundle,
            retrieval_mode=args.retrieval_mode,
        )
    except AblationRunInvalidError as exc:
        logger.error("%s", exc)
        print(f"ABLATION ABORTED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

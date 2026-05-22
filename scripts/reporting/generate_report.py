#!/usr/bin/env python3
"""Generate evaluation_report.md from trace JSONL files."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from eval.curated import (
    CuratedReportError,
    build_curated_summaries,
    iter_cite_entries,
    load_cite_allowlist,
)
from eval.metrics.ci import format_mean_pm_ci
from eval.metrics.efficiency import format_efficiency_table, load_efficiency_from_project
from framework.runtime_dirs import traces_dir as default_traces_dir
from scripts.reporting.analyze_traces import summarize_trace


def discover_trace_files(traces_dir: Path) -> list[Path]:
    """Find aggregate JSONL traces (exclude per_task single-line files)."""
    files = sorted(traces_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p for p in files if "_" in p.stem and p.parent.name == "traces"]


def _parse_config_dataset(stem: str) -> tuple[str, str]:
    """Parse ``D_humaneval_20260517T...`` into config and dataset."""
    match = re.match(r"^([ABCD])_(\w+)_", stem)
    if match:
        return match.group(1), match.group(2)
    parts = stem.split("_", 2)
    if len(parts) >= 2:
        return parts[0], parts[1]
    return stem, "unknown"


def _curated_report_lines(
    *,
    traces_dir: Path,
    allowlist_path: Path | None,
) -> list[str]:
    """Build markdown section for allowlisted runs with multi-seed CIs."""
    allowlist = load_cite_allowlist(allowlist_path)
    groups = build_curated_summaries(allowlist, traces_dir=traces_dir)
    cited_ids = {entry.run_id for entry in iter_cite_entries(allowlist)} - set(
        allowlist.excluded_run_ids
    )

    lines = [
        "## Curated results (allowlist)",
        "",
        f"Allowlist: `{allowlist_path or _PROJECT_ROOT / 'configs' / 'reporting' / 'cite_allowlist.yaml'}`",
        "",
        "| Config | Dataset | Seeds | SR (mean ± 95% CI) | CER (mean ± 95% CI) | Included runs |",
        "|--------|---------|-------|--------------------|---------------------|------------|",
    ]
    for group in groups:
        seeds = ",".join(str(s) for s in group.seeds)
        runs = ", ".join(f"`{rid}`" for rid in group.run_ids)
        lines.append(
            f"| {group.config} | {group.dataset} | {seeds} | "
            f"{format_mean_pm_ci(group.sr_ci)} | {format_mean_pm_ci(group.cer_ci)} | {runs} |"
        )

    lines.extend(
        [
            "",
            "### Excluded runs",
            "",
        ]
    )
    if allowlist.excluded_run_ids:
        for run_id in allowlist.excluded_run_ids:
            lines.append(f"- `{run_id}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "### Allowlisted run ids", ""])
    for run_id in sorted(cited_ids):
        lines.append(f"- `{run_id}`")
    return lines


def generate_report(
    traces_dir: Path | None = None,
    *,
    output_path: Path | None = None,
    checkpoint_dir: Path | None = None,
    curated: bool = True,
    allowlist_path: Path | None = None,
    include_all_traces: bool = False,
) -> Path:
    """Write markdown report with SR/CER, failures, and retry stats."""
    resolved_traces = traces_dir or default_traces_dir()
    output_path = output_path or (_PROJECT_ROOT / "evaluation_report.md")
    ckpt = str(checkpoint_dir) if checkpoint_dir else None

    lines = [
        "# Evaluation Report",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
    ]

    if curated:
        lines.extend(_curated_report_lines(traces_dir=resolved_traces, allowlist_path=allowlist_path))
        lines.append("")

    trace_files: list[Path] = []
    if include_all_traces or not curated:
        trace_files = discover_trace_files(resolved_traces)
        summaries: list[dict] = []
        for path in trace_files:
            try:
                summaries.append(summarize_trace(str(path), checkpoint_dir=ckpt))
            except (OSError, ValueError) as exc:
                summaries.append({"trace_path": str(path), "error": str(exc)})

        lines.extend(
            [
                "## Aggregate runs (JSONL)",
                "",
                "| Config | Dataset | n | SR (%) | CER (%) | Tokens | Latency (ms) | LLM calls | Est. USD | Contradictions |",
                "|--------|---------|---|--------|---------|--------|--------------|-----------|----------|----------------|",
            ]
        )

        for item in summaries:
            if "error" in item:
                lines.append(
                    f"| — | — | — | — | — | — | — | — | — | {item['error'][:40]} |"
                )
                continue
            path = Path(item["trace_path"])
            config, dataset = _parse_config_dataset(path.stem)
            contradictions = item.get("contradictions", 0)
            lines.append(
                f"| {config} | {dataset} | {item['n']} | {item['sr']:.1f} | "
                f"{item['cer']:.1f} | {item.get('tokens_total', 0)} | "
                f"{item.get('latency_ms_total', 0)} | {item.get('llm_calls', 0)} | "
                f"{item.get('estimated_usd', 0.0):.4f} | {contradictions} |"
            )

        lines.extend(["", "## Self-check failure counts", ""])
        for item in summaries:
            if "error" in item:
                continue
            path = Path(item["trace_path"])
            config, dataset = _parse_config_dataset(path.stem)
            failures = item.get("self_check_failures") or {}
            if not failures:
                lines.append(f"- **{config}/{dataset}**: (no checkpoint data)")
                continue
            parts = ", ".join(f"{k}={v}" for k, v in sorted(failures.items()))
            lines.append(f"- **{config}/{dataset}**: {parts}")

        lines.extend(["", "## Retry curves (per task)", ""])
        for item in summaries:
            if "error" in item:
                continue
            path = Path(item["trace_path"])
            config, dataset = _parse_config_dataset(path.stem)
            curves = item.get("retry_curves") or []
            if not curves:
                continue
            avg = sum(c["attempts"] for c in curves) / len(curves)
            solved = sum(1 for c in curves if c.get("solved"))
            lines.append(
                f"- **{config}/{dataset}**: tasks={len(curves)} "
                f"avg_attempts={avg:.2f} solved={solved}"
            )

        lines.extend(
            [
                "",
                "## Sample trace files",
                "",
            ]
        )
        for path in trace_files[:5]:
            lines.append(f"- `{path}`")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(description="Generate evaluation report")
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=None,
        help="Directory containing JSONL traces (default: var/traces)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output markdown path (default: ./evaluation_report.md)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help="Checkpoint directory for decision-log analysis",
    )
    parser.add_argument(
        "--curated",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include only allowlisted runs with manifest + quality validation (default: on)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Also include all discovered trace JSONL files (non-curated table)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="Path to cite_allowlist.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate curated runs only; do not write the report file",
    )
    parser.add_argument(
        "--efficiency",
        action="store_true",
        help="Append efficiency table (tokens/latency/cost per task) from included runs",
    )
    args = parser.parse_args(argv)

    traces_dir = args.traces_dir or default_traces_dir()

    if args.curated or args.dry_run:
        try:
            groups = build_curated_summaries(
                load_cite_allowlist(args.allowlist),
                traces_dir=traces_dir,
            )
        except CuratedReportError as exc:
            print(f"CURATED REPORT ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Curated validation OK: {len(groups)} group(s), "
              f"{sum(len(g.runs) for g in groups)} run(s)")
        if args.dry_run and not args.efficiency:
            return 0

    if args.efficiency:
        eff_rows = load_efficiency_from_project(
            traces_dir=traces_dir,
            allowlist_path=args.allowlist,
        )
        print(format_efficiency_table(eff_rows))
        if args.dry_run:
            return 0

    out = generate_report(
        traces_dir,
        output_path=args.output,
        checkpoint_dir=args.checkpoint_dir,
        curated=args.curated,
        allowlist_path=args.allowlist,
        include_all_traces=args.all,
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

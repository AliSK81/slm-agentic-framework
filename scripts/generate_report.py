#!/usr/bin/env python3
"""Generate thesis_evaluation_report.md from trace JSONL files."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scripts.analyze_traces import summarize_trace


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


def generate_report(
    traces_dir: Path | None = None,
    *,
    output_path: Path | None = None,
    checkpoint_dir: Path | None = None,
) -> Path:
    """Write markdown report with SR/CER, failures, and retry stats."""
    traces_dir = traces_dir or (_PROJECT_ROOT / "traces")
    output_path = output_path or (_PROJECT_ROOT / "thesis_evaluation_report.md")
    ckpt = str(checkpoint_dir) if checkpoint_dir else None

    trace_files = discover_trace_files(traces_dir)
    summaries: list[dict] = []
    for path in trace_files:
        try:
            summaries.append(summarize_trace(str(path), checkpoint_dir=ckpt))
        except (OSError, ValueError) as exc:
            summaries.append({"trace_path": str(path), "error": str(exc)})

    lines = [
        "# Thesis Evaluation Report",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Aggregate runs (JSONL)",
        "",
        "| Config | Dataset | n | SR (%) | CER (%) | Contradictions |",
        "|--------|---------|---|--------|---------|----------------|",
    ]

    for item in summaries:
        if "error" in item:
            lines.append(f"| — | — | — | — | — | {item['error'][:40]} |")
            continue
        path = Path(item["trace_path"])
        config, dataset = _parse_config_dataset(path.stem)
        contradictions = item.get("contradictions", 0)
        lines.append(
            f"| {config} | {dataset} | {item['n']} | {item['sr']:.1f} | "
            f"{item['cer']:.1f} | {contradictions} |"
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
    parser = argparse.ArgumentParser(description="Generate thesis evaluation report")
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=None,
        help="Directory containing JSONL traces (default: ./traces)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output markdown path (default: ./thesis_evaluation_report.md)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=None,
        help="Checkpoint directory for decision-log analysis",
    )
    args = parser.parse_args(argv)

    out = generate_report(
        args.traces_dir,
        output_path=args.output,
        checkpoint_dir=args.checkpoint_dir,
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

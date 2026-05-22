#!/usr/bin/env python3
"""Copy allowlisted trace artifacts into artifacts/repro_bundle/ (no secrets, no workspaces)."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval.curated import (
    assert_text_has_no_secrets,
    collect_cited_artifacts,
    load_cite_allowlist,
)


def make_repro_bundle(
    *,
    allowlist_path: Path | None = None,
    traces_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Validate allowlisted runs and copy JSONL, manifests, and decision logs into a bundle.

    Inputs:
        allowlist_path: Path to cite_allowlist.yaml.
        traces_dir: Source traces directory (default ./traces).
        output_dir: Bundle root (default ./artifacts/repro_bundle).

    Outputs:
        Path to the bundle directory.

    Side effects:
        Creates output_dir; writes MANIFEST_INDEX.md; copies allowlisted files only.
    """
    traces_dir = traces_dir or (_PROJECT_ROOT / "traces")
    output_dir = output_dir or (_PROJECT_ROOT / "artifacts" / "repro_bundle")
    allowlist = load_cite_allowlist(allowlist_path)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts = collect_cited_artifacts(allowlist, traces_dir=traces_dir)
    index_lines = [
        "# Reproducibility bundle index",
        "",
        f"Source traces: `{traces_dir.resolve()}`",
        "",
        "| Bundle path | Source |",
        "|-------------|--------|",
    ]

    for src, rel in artifacts:
        text = src.read_text(encoding="utf-8")
        assert_text_has_no_secrets(text, label=rel)
        dest = output_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        index_lines.append(f"| `{rel}` | `{src}` |")

    index_path = output_dir / "MANIFEST_INDEX.md"
    index_text = "\n".join(index_lines) + "\n"
    assert_text_has_no_secrets(index_text, label="MANIFEST_INDEX.md")
    index_path.write_text(index_text, encoding="utf-8")
    return output_dir


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(description="Build curated reproducibility bundle")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="Path to cite_allowlist.yaml (default: configs/cite_allowlist.yaml)",
    )
    parser.add_argument(
        "--traces-dir",
        type=Path,
        default=None,
        help="Traces directory (default: ./traces)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Bundle output directory (default: ./artifacts/repro_bundle)",
    )
    args = parser.parse_args(argv)

    out = make_repro_bundle(
        allowlist_path=args.allowlist,
        traces_dir=args.traces_dir,
        output_dir=args.output,
    )
    print(f"Wrote bundle to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

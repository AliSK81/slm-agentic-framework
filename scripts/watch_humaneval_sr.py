"""Compatibility wrapper for scripts.benchmark.watch_humaneval_sr."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.benchmark.watch_humaneval_sr import report


if __name__ == "__main__":
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    raise SystemExit(report(arg))

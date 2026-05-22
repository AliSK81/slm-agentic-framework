"""Compatibility wrapper for scripts.reporting.diagnose_e2e."""

from __future__ import annotations

import sys

from scripts.reporting.diagnose_e2e import diagnose


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <log_path>")
        raise SystemExit(1)
    diagnose(sys.argv[1])

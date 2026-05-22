"""Compatibility wrapper for scripts.reporting.generate_report."""

from scripts.reporting.generate_report import *  # noqa: F401,F403
from scripts.reporting.generate_report import main


if __name__ == "__main__":
    raise SystemExit(main())

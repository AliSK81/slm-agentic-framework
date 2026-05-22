"""Compatibility wrapper for scripts.reporting.analyze_traces."""

from scripts.reporting.analyze_traces import *  # noqa: F401,F403
from scripts.reporting.analyze_traces import main


if __name__ == "__main__":
    raise SystemExit(main())

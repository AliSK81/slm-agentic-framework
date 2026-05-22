"""Compatibility wrapper for scripts.benchmark.smoke_test."""

from scripts.benchmark.smoke_test import *  # noqa: F401,F403
from scripts.benchmark.smoke_test import main


if __name__ == "__main__":
    raise SystemExit(main())

"""Compatibility wrapper for scripts.benchmark.run_benchmark_batch."""

from scripts.benchmark.run_benchmark_batch import *  # noqa: F401,F403
from scripts.benchmark.run_benchmark_batch import main


if __name__ == "__main__":
    raise SystemExit(main())

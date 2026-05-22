"""Compatibility wrapper for scripts.reporting.make_repro_bundle."""

from scripts.reporting.make_repro_bundle import *  # noqa: F401,F403
from scripts.reporting.make_repro_bundle import main


if __name__ == "__main__":
    raise SystemExit(main())

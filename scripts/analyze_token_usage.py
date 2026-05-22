"""Compatibility wrapper for scripts.maintenance.analyze_token_usage."""

from scripts.maintenance.analyze_token_usage import *  # noqa: F401,F403
from scripts.maintenance.analyze_token_usage import main


if __name__ == "__main__":
    raise SystemExit(main())

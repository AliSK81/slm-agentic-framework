"""Compatibility wrapper for scripts.maintenance.sync_discriminative_allowlist."""

from scripts.maintenance.sync_discriminative_allowlist import *  # noqa: F401,F403
from scripts.maintenance.sync_discriminative_allowlist import main


if __name__ == "__main__":
    raise SystemExit(main())

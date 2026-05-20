"""Aviona daily-driver SLM profile selection."""

from __future__ import annotations

import os

DAILY_DRIVER_PROFILE = "aviona-daily"
DAILY_DRIVER_BUNDLE = "aviona_daily"


def apply_daily_driver_profiles() -> None:
    """Set planner/executor profiles to the Aviona daily-driver unless already overridden.

    Uses ``setdefault`` so thesis eval profiles and explicit ``PLANNER_PROFILE`` env
    values are not clobbered.
    """
    os.environ.setdefault("PLANNER_PROFILE", DAILY_DRIVER_PROFILE)
    os.environ.setdefault("EXECUTOR_PROFILE", DAILY_DRIVER_PROFILE)

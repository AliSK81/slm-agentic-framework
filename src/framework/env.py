"""Project environment loading."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"


def load_project_env() -> None:
    """Load ``.env`` from the repo root, overriding stale shell exports."""
    if _ENV_FILE.is_file():
        load_dotenv(_ENV_FILE, override=True)

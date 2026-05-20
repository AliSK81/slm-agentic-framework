"""Aviona environment loading (global secrets then project ``.env``)."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def aviona_global_env_path() -> Path:
    """Return ``%USERPROFILE%\\.aviona\\.env`` (Windows) or ``~/.aviona/.env``."""
    return Path.home() / ".aviona" / ".env"


def load_aviona_env(cwd: Path | None = None) -> None:
    """Load secrets without echoing values.

    Resolution order (later wins):
      1. ``~/.aviona/.env`` — user-global Aviona secrets
      2. ``<cwd>/.env`` — project-local overrides (when ``cwd`` is set)
      3. Framework repo ``.env`` via :func:`framework.env.load_project_env` when no cwd file

    Never logs or prints secret values.
    """
    global_path = aviona_global_env_path()
    if global_path.is_file():
        load_dotenv(global_path, override=False)

    project_root = (cwd or Path.cwd()).resolve()
    project_env = project_root / ".env"
    if project_env.is_file():
        load_dotenv(project_env, override=True)
    else:
        from framework.env import load_project_env

        load_project_env()

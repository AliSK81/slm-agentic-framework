"""Project-local Aviona settings (``.aviona/settings.yaml``)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from aviona.permissions import Mode

logger = logging.getLogger(__name__)

_DEFAULT_COMMANDS = ["pytest", "python", "py_compile", "cat", "ls", "find"]


class AvionaSettings(BaseModel):
    """Settings loaded from ``./.aviona/settings.yaml``."""

    mode: Mode = "default"
    commands: list[str] = Field(default_factory=lambda: list(_DEFAULT_COMMANDS))


def settings_path(cwd: Path) -> Path:
    """Path to the project settings file."""
    return cwd.resolve() / ".aviona" / "settings.yaml"


def load_settings(cwd: Path) -> AvionaSettings:
    """Load settings from ``./.aviona/settings.yaml`` or return defaults."""
    path = settings_path(cwd)
    if not path.is_file():
        return AvionaSettings()
    try:
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        logger.warning("Could not read Aviona settings %s: %s", path, exc)
        return AvionaSettings()
    mode = raw.get("mode", "default")
    if mode not in ("plan", "default", "auto"):
        mode = "default"
    commands = raw.get("commands")
    if not isinstance(commands, list):
        commands = list(_DEFAULT_COMMANDS)
    else:
        commands = [str(item) for item in commands if str(item).strip()]
    return AvionaSettings(mode=mode, commands=commands)

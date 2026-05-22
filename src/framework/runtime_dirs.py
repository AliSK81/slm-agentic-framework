"""Runtime artifact directories under ``var/`` at the repo root."""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = _PROJECT_ROOT / "var"


def runtime_root() -> Path:
    """Return ``var/``, creating it when missing."""
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    return RUNTIME_ROOT


def traces_dir() -> Path:
    """Evaluation traces, manifests, workspaces, and per-task JSON."""
    path = runtime_root() / "traces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    """Framework and e2e log files."""
    path = runtime_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def checkpoints_dir(override: Path | None = None) -> Path:
    """Session checkpoint JSON files."""
    if override is not None:
        path = override
    else:
        env = os.getenv("CHECKPOINT_DIR", "").strip()
        path = Path(env) if env else runtime_root() / "checkpoints"
    path.mkdir(parents=True, exist_ok=True)
    return path

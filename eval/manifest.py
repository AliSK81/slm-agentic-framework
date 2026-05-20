"""Per-run reproducibility manifest (no secrets)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN_FIELD_NAMES = frozenset(
    {"api_key", "apikey", "token", "secret", "secret_key", "password"}
)
_FORBIDDEN_VALUE_MARKERS = ("sk-", "api_key", "bearer ", "secret")


class RunManifest(BaseModel):
    """Metadata describing how an eval run was produced."""

    run_id: str
    config: str
    dataset: str
    n: int
    seed: int
    provider: str
    planner_profile: str
    executor_profile: str
    git_sha: str
    task_ids: list[str]
    task_to_session_map: dict[str, str] = Field(default_factory=dict)
    decisions_file: str = ""
    ablation_flags: dict[str, bool] = Field(default_factory=dict)
    created_at: datetime


def resolve_git_sha(project_root: Path | None = None) -> str:
    """Return ``git rev-parse HEAD`` or ``unknown`` when git is unavailable."""
    root = project_root or _PROJECT_ROOT
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not resolve git SHA: %s", exc)
        return "unknown"
    return completed.stdout.strip()


def manifest_provider_and_profiles() -> tuple[str, str, str]:
    """Resolve active provider and planner/executor profile names from config."""
    src = str(_PROJECT_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from framework.slm.config import active_provider_name
    from framework.slm.registry import resolve_profile_name

    return (
        active_provider_name(),
        resolve_profile_name("planner"),
        resolve_profile_name("executor"),
    )


def write_manifest(
    run_id: str,
    *,
    traces_dir: Path | None = None,
    **kwargs: Any,
) -> Path:
    """Write ``traces/{run_id}.manifest.json`` and return its path.

    Inputs:
        run_id: Stem of the aggregate JSONL file (e.g. ``D_humaneval_20260520T120000Z``).
        traces_dir: Directory for trace artifacts (default ``./traces``).
        **kwargs: Fields for :class:`RunManifest` (except ``run_id``).

    Outputs:
        Path to the written manifest file.

    Side effects:
        Creates ``traces_dir`` if needed; writes JSON to disk.
    """
    root = traces_dir or (_PROJECT_ROOT / "traces")
    root.mkdir(parents=True, exist_ok=True)
    manifest = RunManifest(run_id=run_id, **kwargs)
    path = root / f"{run_id}.manifest.json"
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def assert_manifest_has_no_secrets(payload: dict[str, Any]) -> None:
    """Raise ``ValueError`` when manifest JSON appears to contain secrets."""
    stack: list[tuple[str, Any]] = [("", payload)]
    while stack:
        prefix, value = stack.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                field_path = f"{prefix}.{key}" if prefix else str(key)
                if str(key).lower() in _FORBIDDEN_FIELD_NAMES:
                    raise ValueError(f"secret-like field in manifest: {field_path}")
                stack.append((field_path, child))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                stack.append((f"{prefix}[{index}]", child))
        elif isinstance(value, str):
            lowered = value.lower()
            for marker in _FORBIDDEN_VALUE_MARKERS:
                if marker in lowered and len(value) > 12:
                    raise ValueError(
                        f"secret-like value in manifest at {prefix}: {marker}"
                    )

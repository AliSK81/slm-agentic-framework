"""Load frozen curated task-id lists from configs/."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_CONFIGS_DIR = Path(__file__).resolve().parents[2] / "configs"
_DEFAULT_HARD_IDS_PATH = _CONFIGS_DIR / "humaneval_hard_ids.txt"


@lru_cache(maxsize=8)
def load_curated_ids(ids_path: Path) -> frozenset[str]:
    """Load version-controlled task ids from a text file (``#`` comments skipped)."""
    if not ids_path.is_file():
        return frozenset()
    ids: set[str] = set()
    for line in ids_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ids.add(stripped)
    return frozenset(ids)


def resolve_ids_path(ids_file: str | None) -> Path:
    """Resolve ``ids_file`` relative to ``configs/``."""
    if not ids_file:
        return _DEFAULT_HARD_IDS_PATH
    path = Path(ids_file)
    if path.is_absolute():
        return path
    return _CONFIGS_DIR / path

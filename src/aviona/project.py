"""Project rules loading for Aviona sessions."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_PROJECT_RULES_CHARS = 8000
_RULES_PREFIX = "[PROJECT RULES]"


def locate_rules_file(cwd: Path) -> Path | None:
    """Return the first existing rules file under ``cwd``, or ``None``.

    Preference order: ``./AVIONA.md``, then ``./.aviona/PROJECT.md``.
    """
    root = cwd.resolve()
    candidates = (
        root / "AVIONA.md",
        root / ".aviona" / "PROJECT.md",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_project_rules(cwd: Path) -> list[str]:
    """Load and truncate project rules for injection into session constraints.

    Args:
        cwd: Project workspace root.

    Returns:
        A single-element list with a ``[PROJECT RULES]`` segment, or ``[]`` when
        no rules file exists or the file is empty.
    """
    path = locate_rules_file(cwd)
    if path is None:
        return []
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("Could not read project rules %s: %s", path, exc)
        return []
    if not text:
        return []
    if len(text) > MAX_PROJECT_RULES_CHARS:
        text = text[:MAX_PROJECT_RULES_CHARS] + "\n…(truncated)"
    return [f"{_RULES_PREFIX}\n{text}"]

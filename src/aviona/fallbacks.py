"""Deterministic Aviona fallbacks when the agent turn fails verification."""

from __future__ import annotations

import re
from pathlib import Path

from aviona.effects import TurnEffects, infer_target_file
from framework.tools.file_tools import read_file

_PROJECT_FILES = ("README.md", "AVIONA.md", "pyproject.toml", "main.py", "calculator.py")


def _first_paragraph(text: str, *, max_chars: int = 500) -> str:
    """Return the first non-heading paragraph from markdown or plain text."""
    title = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title:
        heading = title.group(1).strip()
        if heading:
            return heading

    lines: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line or line.startswith("#"):
            if lines:
                break
            continue
        if re.match(r"^[A-Za-z]:\\", line) or re.match(r"^(cd |pip |python |\.\./)", line):
            continue
        if line.startswith("|") or line.startswith("---"):
            continue
        lines.append(line)
    body = " ".join(lines).strip()
    if not body and text.strip():
        body = text.strip().splitlines()[0].lstrip("#").strip()
    if len(body) <= max_chars:
        return body
    return body[: max_chars - 3].rstrip() + "..."


def build_project_summary(workspace: Path) -> str | None:
    """Build a short project summary from common repo files.

    Args:
        workspace: Project root directory.

    Returns:
        Multi-line summary text, or ``None`` when no useful files exist.
    """
    root = workspace.resolve()
    if not root.is_dir():
        return None

    sections: list[str] = []
    for name in _PROJECT_FILES:
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        snippet = _first_paragraph(text)
        sections.append(f"{name}: {snippet}")

    if sections:
        return "Project overview (from workspace files):\n\n" + "\n\n".join(sections)

    files = sorted(p.name for p in root.iterdir() if p.is_file())[:10]
    if files:
        return (
            "This workspace has no README yet. Top-level files: "
            + ", ".join(files)
            + ". Try: explain main.py"
        )
    return None


def try_read_content_fallback(goal: str, workspace: Path) -> TurnEffects | None:
    """Read a target file directly when the agent did not call read_file.

    Args:
        goal: Original user goal line.
        workspace: Project root.

    Returns:
        Satisfied ``TurnEffects`` when a target file was read, else ``None``.
    """
    target = infer_target_file(goal, workspace)
    if not target:
        return None
    result = read_file(target, workspace)
    if not result.ok or not result.content:
        return None
    body = result.content.strip()
    detail = body if len(body) <= 2000 else body[:1997] + "..."
    return TurnEffects(
        satisfied=True,
        user_detail=detail,
        read_paths=[target],
    )


def try_explain_fallback(workspace: Path) -> TurnEffects | None:
    """Summarize the project from README and key files when the agent failed.

    Args:
        workspace: Project root.

    Returns:
        Satisfied ``TurnEffects`` with summary text, or ``None``.
    """
    summary = build_project_summary(workspace)
    if not summary:
        return None
    return TurnEffects(satisfied=True, user_detail=summary)

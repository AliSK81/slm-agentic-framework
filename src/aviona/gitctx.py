"""Read-only git repository context for Aviona session startup."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from framework.error_control.sandbox import safe_execute

logger = logging.getLogger(__name__)

_GIT_BRANCH_CMD = "git branch --show-current"
_GIT_STATUS_CMD = "git status --porcelain"


class GitStatus(BaseModel):
    """Parsed git branch and changed-file list."""

    branch: str = ""
    changed_files: list[str] = Field(default_factory=list)


def _is_git_repo(cwd: Path) -> bool:
    """Return True when ``cwd`` looks like a git working tree."""
    root = cwd.resolve()
    git_path = root / ".git"
    return git_path.is_dir() or git_path.is_file()


def _parse_porcelain(stdout: str) -> list[str]:
    """Extract changed file paths from ``git status --porcelain`` output."""
    files: list[str] = []
    for line in stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            files.append(path)
    return files


def git_status(cwd: Path) -> GitStatus:
    """Return branch name and changed files via sandboxed read-only git commands.

    Uses only ``git branch --show-current`` and ``git status --porcelain`` through
    :func:`framework.error_control.sandbox.safe_execute`. Non-git directories
    return an empty status without error.

    Args:
        cwd: Project workspace root.

    Returns:
        ``GitStatus`` with branch and changed file paths (may be empty).
    """
    root = cwd.resolve()
    if not _is_git_repo(root):
        return GitStatus()

    branch_result = safe_execute(_GIT_BRANCH_CMD, root, timeout_s=10)
    if branch_result.blocked:
        logger.warning("git branch blocked by sandbox")
        return GitStatus()
    branch = branch_result.stdout.strip() if branch_result.ok else ""

    status_result = safe_execute(_GIT_STATUS_CMD, root, timeout_s=10)
    if status_result.blocked:
        logger.warning("git status blocked by sandbox")
        return GitStatus(branch=branch)
    if not status_result.ok:
        return GitStatus(branch=branch)

    return GitStatus(
        branch=branch,
        changed_files=_parse_porcelain(status_result.stdout),
    )


def format_git_summary(status: GitStatus) -> str | None:
    """One-line REPL summary: ``git: main · 3 changed``."""
    if not status.branch and not status.changed_files:
        return None
    branch = status.branch or "(detached)"
    count = len(status.changed_files)
    if count:
        noun = "file" if count == 1 else "files"
        return f"git: {branch} · {count} changed {noun}"
    return f"git: {branch} · clean"


def git_anchor_segment(status: GitStatus) -> str | None:
    """Tiny anchor segment for working-memory injection."""
    summary = format_git_summary(status)
    if summary is None:
        return None
    return f"[GIT] {summary}"

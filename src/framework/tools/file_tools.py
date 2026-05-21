"""Read/write/edit file tools with write-guard and AST gate."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from pydantic import BaseModel

from framework.error_control.truncation import truncate

logger = logging.getLogger(__name__)


class FileResult(BaseModel):
    """Result of a file tool operation."""

    ok: bool
    message: str
    content: str | None = None


def _resolve_path(file_path: str, workspace: Path) -> Path | None:
    workspace = workspace.resolve()
    candidate = Path(file_path)
    if candidate.is_absolute():
        target = candidate.resolve()
    else:
        target = (workspace / file_path).resolve()
    try:
        target.relative_to(workspace)
    except ValueError:
        return None
    return target


def read_file(file_path: str, workspace: Path) -> FileResult:
    """Read file under workspace with truncation applied."""
    target = _resolve_path(file_path, workspace)
    if target is None:
        return FileResult(ok=False, message="path outside workspace")
    if not target.is_file():
        return FileResult(ok=False, message=f"file not found: {file_path}")
    content = target.read_text(encoding="utf-8")
    capped = truncate(content, "read_file")
    return FileResult(ok=True, message="ok", content=capped)


def write_file(file_path: str, content: str, workspace: Path) -> FileResult:
    """Create a new file; refuse if the path already exists (write-guard)."""
    target = _resolve_path(file_path, workspace)
    if target is None:
        return FileResult(ok=False, message="path outside workspace")
    if target.exists():
        return FileResult(
            ok=False,
            message=(
                f"Write guard: '{file_path}' already exists. "
                "Use edit_file instead:\n"
                f'edit_file(file_path="{file_path}", '
                f'old_string="<exact existing text>", '
                f'new_string="<updated text>")'
            ),
        )
    if target.suffix in (".py", ".pyw"):
        try:
            ast.parse(content, filename=str(target))
        except SyntaxError as exc:
            return FileResult(
                ok=False,
                message=f"AST gate rejected write: line {exc.lineno}: {exc.msg}",
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return FileResult(ok=True, message="created")


def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    workspace: Path,
) -> FileResult:
    """Replace exactly one occurrence; AST-gate Python files before write."""
    target = _resolve_path(file_path, workspace)
    if target is None:
        return FileResult(ok=False, message="path outside workspace")
    if not target.is_file():
        return FileResult(ok=False, message=f"file not found: {file_path}")

    original = target.read_text(encoding="utf-8")
    count = original.count(old_string)
    if count == 0:
        return FileResult(ok=False, message="old_string not found in file")
    if count > 1:
        return FileResult(
            ok=False,
            message=f"old_string appears {count} times; must be unique",
        )

    updated = original.replace(old_string, new_string, 1)
    if target.suffix == ".py" or target.suffix == ".pyw":
        try:
            ast.parse(updated, filename=str(target))
        except SyntaxError as exc:
            snippet = updated[max(0, (exc.lineno or 1) - 2) : (exc.lineno or 1) + 2]
            return FileResult(
                ok=False,
                message=(
                    f"AST gate rejected edit: line {exc.lineno}: {exc.msg}\n"
                    f"Snippet:\n{snippet}"
                ),
            )

    target.write_text(updated, encoding="utf-8")
    return FileResult(ok=True, message="updated")

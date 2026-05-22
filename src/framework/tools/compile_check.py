"""Python compile and syntax checking."""

from __future__ import annotations

import ast
import logging
import py_compile
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CompileResult(BaseModel):
    """Result of py_compile / ast.parse check."""

    ok: bool
    errors: list[str] = Field(default_factory=list)
    file_path: str = ""


def _format_syntax_error(exc: SyntaxError, file_path: str) -> str:
    line = exc.lineno or 0
    msg = exc.msg or str(exc)
    return f"line {line}: {msg} ({file_path})"


def py_compile_check(code_or_path: str) -> CompileResult:
    """Run ast.parse and py_compile on source text or an existing file path."""
    path = Path(code_or_path)
    if path.is_file():
        file_path = str(path.resolve())
        source = path.read_text(encoding="utf-8")
    else:
        file_path = "<string>"
        source = code_or_path

    try:
        ast.parse(source, filename=file_path)
    except SyntaxError as exc:
        return CompileResult(
            ok=False,
            errors=[_format_syntax_error(exc, file_path)],
            file_path=file_path,
        )

    try:
        if path.is_file():
            py_compile.compile(file_path, doraise=True)
        else:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(source)
                tmp_path = tmp.name
            try:
                py_compile.compile(tmp_path, doraise=True)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
    except py_compile.PyCompileError as exc:
        # PyCompileError wraps the original exception; find it in args
        syntax_exc = next((a for a in exc.args if isinstance(a, Exception)), None)
        if isinstance(syntax_exc, SyntaxError):
            return CompileResult(
                ok=False,
                errors=[_format_syntax_error(syntax_exc, file_path)],
                file_path=file_path,
            )
        return CompileResult(
            ok=False,
            errors=[str(exc)],
            file_path=file_path,
        )

    return CompileResult(ok=True, errors=[], file_path=file_path)

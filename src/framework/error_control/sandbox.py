"""Allow-listed subprocess execution."""

from __future__ import annotations

import logging
import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel

from framework.error_control.truncation import truncate

logger = logging.getLogger(__name__)

SAFE_COMMANDS: frozenset[str] = frozenset(
    {
        "python",
        "python3",
        "pytest",
        "py_compile",
        "cat",
        "ls",
        "find",
        "diff",
        "echo",
        "ast",
        "docker",
    }
)


class SubprocessResult(BaseModel):
    """Result of a sandboxed subprocess invocation."""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    blocked: bool = False
    message: str = ""


def _command_allowed(cmd: str) -> bool:
    parts = shlex.split(cmd, posix=False)
    if not parts:
        return False
    raw = parts[0].replace('"', "").replace("'", "")
    executable = Path(raw).name.lower()
    if executable.endswith(".exe"):
        executable = executable[:-4]
    return executable in SAFE_COMMANDS


def safe_execute(cmd: str, cwd: Path, timeout_s: int = 30) -> SubprocessResult:
    """Allow-list check → subprocess → truncated stdout/stderr."""
    if not _command_allowed(cmd):
        logger.warning("Blocked command: %s", cmd)
        return SubprocessResult(
            ok=False,
            blocked=True,
            message=f"Command not in allow-list: {cmd.split()[0]}",
            exit_code=-1,
        )
    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        tool = "pytest_run" if "pytest" in cmd else "py_compile"
        stdout = truncate(completed.stdout or "", tool)
        stderr = truncate(completed.stderr or "", tool)
        return SubprocessResult(
            ok=completed.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode,
        )
    except subprocess.TimeoutExpired:
        return SubprocessResult(
            ok=False,
            message="timeout",
            exit_code=-1,
        )
    except OSError as exc:
        logger.warning("safe_execute failed: %s", exc)
        return SubprocessResult(ok=False, message=str(exc), exit_code=-1)

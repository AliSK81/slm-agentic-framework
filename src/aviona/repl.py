"""Interactive Aviona REPL — one bounded turn per user line."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable, Iterator, Sequence

from aviona.debug_log import (
    close_debug_log,
    enable_debug_log,
    is_debug_enabled,
    log_repl_user,
)
from aviona.console import write_line
from aviona.gitctx import format_git_summary
from aviona.session import AvionaSession, TurnResult

logger = logging.getLogger(__name__)

Reader = Callable[[str], str]
Writer = Callable[[str], object]

_HELP_TEXT = """Aviona commands:
  /help          - show this help
  /exit          - leave the REPL
  /mode          - show current permission mode
  /mode plan     - read-only (no writes / side-effect shell)
  /mode default  - ask before side-effect shell
  /mode auto     - allow cwd writes and allowlisted shell
Ask questions (explain the codebase), list/read files, or request edits."""


class ScriptedReader:
    """Test helper: yield lines from a script then raise EOFError."""

    def __init__(self, lines: Sequence[str]) -> None:
        self._lines: Iterator[str] = iter(lines)

    def __call__(self, prompt: str) -> str:
        _ = prompt
        try:
            return next(self._lines)
        except StopIteration as exc:
            raise EOFError("script exhausted") from exc


def default_reader(prompt: str) -> str:
    """Read one REPL line using ``prompt_toolkit`` when available, else ``input()``."""
    if not sys.stdin.isatty():
        return input(prompt)

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
    except ImportError:
        return input(prompt)

    if not hasattr(default_reader, "_session"):
        default_reader._session = PromptSession(history=InMemoryHistory())  # type: ignore[attr-defined]
    session = default_reader._session  # type: ignore[attr-defined]
    return session.prompt(prompt)


def _handle_meta(
    line: str,
    *,
    writer: Writer,
    session: AvionaSession,
) -> bool:
    """Handle ``/help``, ``/exit``, ``/mode``. Return True when the REPL should stop."""
    lowered = line.strip().lower()
    if lowered == "/help":
        writer(_HELP_TEXT)
        return False
    if lowered == "/exit":
        return True
    if lowered == "/mode" or lowered.startswith("/mode "):
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 1:
            writer(f"mode: {session.permission_gate.mode}")
            return False
        mode = parts[1].strip().lower()
        if mode in ("plan", "default", "auto"):
            session.set_mode(mode)  # type: ignore[arg-type]
            writer(f"mode: {mode}")
        else:
            writer("usage: /mode plan|default|auto")
        return False
    return False


def run_repl(
    session: AvionaSession,
    *,
    reader: Reader | None = None,
    writer: Writer | None = None,
    prompt: str = "aviona> ",
    run_turn: Callable[[str], TurnResult] | None = None,
    debug: bool = False,
) -> int:
    """Run the interactive REPL until ``/exit`` or EOF.

    Every non-command user line runs exactly one ``run_turn`` (no phrase routing).
    """
    read = reader or default_reader
    write = writer or write_line
    turn = run_turn or session.run_turn
    session.set_confirm_reader(read)

    debug_path = None
    if debug:
        debug_path = enable_debug_log(
            workspace=session.workspace,
            session_id=session._session_id,
        )
        write("")
        write("Debug mode enabled")
        write(f"Logging to: {debug_path}")
        write("")

    write(f"Aviona - workspace: {session.workspace}")
    write(f"mode: {session.permission_gate.mode}")
    if debug:
        write("Debug mode")
    git_line = format_git_summary(session.git_status)
    if git_line:
        write(git_line)
    write("Type /help for commands.")

    while True:
        try:
            line = read(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            write("")
            if debug:
                close_debug_log()
            return 0

        if not line:
            continue

        if line.startswith("/"):
            if _handle_meta(line, writer=write, session=session):
                if debug:
                    close_debug_log()
                return 0
            continue

        if is_debug_enabled():
            log_repl_user(line)

        write("...")
        started = time.perf_counter()
        if is_debug_enabled():
            from aviona.debug_log import log_turn_start

            log_turn_start(goal=line, session_id=session._session_id)
        try:
            result = turn(line)
        except KeyboardInterrupt:
            write("turn cancelled")
            continue
        except Exception as exc:  # noqa: BLE001 — REPL must survive turn errors
            logger.exception("REPL turn failed: %s", exc)
            write(f"error: {exc}")
            continue

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        write(result.status)
        if result.detail:
            for detail_line in result.detail.splitlines():
                write(f"  {detail_line}")
        if debug:
            seconds = elapsed_ms / 1000.0
            if seconds >= 10:
                write(f"* Worked for {seconds:.0f}s")
            else:
                write(f"* Worked for {seconds:.1f}s")
    return 0

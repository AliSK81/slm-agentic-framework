"""Interactive Aviona REPL — one bounded turn per user line."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Sequence
from aviona.session import AvionaSession, TurnResult

logger = logging.getLogger(__name__)

Reader = Callable[[str], str]
Writer = Callable[[str], object]

_HELP_TEXT = """Aviona commands:
  /help   — show this help
  /exit   — leave the REPL
  /mode   — execution mode (wired in AVIONA-7)
Type any other line to run one bounded agent turn."""


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
) -> bool:
    """Handle ``/help``, ``/exit``, ``/mode``. Return True when the REPL should stop."""
    lowered = line.strip().lower()
    if lowered == "/help":
        writer(_HELP_TEXT)
        return False
    if lowered == "/exit":
        return True
    if lowered == "/mode":
        writer("mode: default (AVIONA-7 will add selectable modes)")
        return False
    return False


def run_repl(
    session: AvionaSession,
    *,
    reader: Reader | None = None,
    writer: Writer | None = None,
    prompt: str = "aviona> ",
    run_turn: Callable[[str], TurnResult] | None = None,
) -> int:
    """Run the interactive REPL until ``/exit`` or EOF.

    Args:
        session: Shared ``AvionaSession`` for all turns.
        reader: Line reader (inject ``ScriptedReader`` in tests).
        writer: Status/output sink (defaults to ``print``).
        prompt: Input prompt string.
        run_turn: Optional override for ``session.run_turn`` (testing).

    Returns:
        Process exit code (0 on normal exit).
    """
    read = reader or default_reader
    write = writer or print
    turn = run_turn or session.run_turn

    write(f"Aviona — workspace: {session.workspace}")
    write("Type /help for commands.")

    while True:
        try:
            line = read(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            write("")
            return 0

        if not line:
            continue

        if line.startswith("/"):
            if _handle_meta(line, writer=write):
                return 0
            continue

        try:
            result = turn(line)
        except KeyboardInterrupt:
            write("turn cancelled")
            continue
        except Exception as exc:  # noqa: BLE001 — REPL must survive turn errors
            logger.exception("REPL turn failed: %s", exc)
            write(f"error: {exc}")
            continue

        write(result.status)
    return 0

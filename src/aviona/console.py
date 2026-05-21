"""Console output helpers — safe on Windows cp1252 and piped stdout."""

from __future__ import annotations

import sys

_ASCII_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("\u2713", "ok"),  # checkmark
    ("\u273b", "*"),  # heavy asterisk (Claude-style timing marker)
    ("\u2026", "..."),  # ellipsis
    ("\u00b7", "|"),  # middle dot
    ("\u2014", "-"),  # em dash
    ("\u2013", "-"),  # en dash
)


def ascii_safe(text: str) -> str:
    """Replace common Unicode UI symbols with ASCII equivalents."""
    for src, dst in _ASCII_REPLACEMENTS:
        text = text.replace(src, dst)
    return text


def configure_stdio() -> None:
    """Prefer UTF-8 stdout/stderr with replacement on unsupported characters."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            pass


def write_line(text: str, *, file=None) -> None:
    """Write one line without raising ``UnicodeEncodeError``."""
    stream = file or sys.stdout
    safe = ascii_safe(text)
    try:
        print(safe, file=stream, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        fallback = safe.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(fallback, file=stream, flush=True)

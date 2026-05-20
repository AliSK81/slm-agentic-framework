"""Aviona console output unit tests."""

from __future__ import annotations

from aviona.console import ascii_safe


def test_ascii_safe_replaces_unicode_ui_symbols() -> None:
    """Common REPL symbols map to ASCII for Windows consoles."""
    text = "ok | 3 steps \u2713 \u00b7 \u2014 \u2026"
    safe = ascii_safe(text)
    assert "\u2713" not in safe
    assert "\u00b7" not in safe
    assert "\u2014" not in safe
    assert "\u2026" not in safe
    assert "ok" in safe
    assert "|" in safe

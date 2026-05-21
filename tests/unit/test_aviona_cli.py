"""Aviona CLI unit tests — no network, no API keys."""

from __future__ import annotations

import argparse
import sys

import pytest

from aviona import __version__
from aviona.cli import build_parser, main


def test_build_parser_has_version_and_doctor_subcommand() -> None:
    """Parser exposes --version and a doctor subcommand."""
    parser = build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert any(action.dest == "version" for action in parser._actions)
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"


def test_main_help_exits_zero(capsys) -> None:
    """main(['--help']) returns 0 and prints usage."""
    code = main(["--help"])
    assert code == 0
    captured = capsys.readouterr()
    assert "aviona" in captured.out.lower() or "usage" in captured.out.lower()


def test_main_version_exits_zero(capsys) -> None:
    """main(['--version']) returns 0 and prints the package version."""
    code = main(["--version"])
    assert code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_main_doctor_delegates_to_run_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    """doctor subcommand runs probe-only diagnostics."""
    monkeypatch.setattr("aviona.cli.load_aviona_env", lambda _cwd=None: None)
    monkeypatch.setattr("aviona.cli.run_doctor", lambda: 0)
    assert main(["doctor"]) == 0


def test_main_yes_flag_sets_auto_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--yes forces permission mode auto before REPL starts."""
    captured: dict[str, str] = {}

    class _Session:
        def set_mode(self, mode: str) -> None:
            captured["mode"] = mode

    monkeypatch.setattr("aviona.cli.ensure_slm_api_key_configured", lambda: None)
    monkeypatch.setattr("aviona.cli.load_aviona_env", lambda _cwd=None: None)
    monkeypatch.setattr("aviona.cli.run_repl", lambda _s, debug=False: 0)
    monkeypatch.setattr("aviona.cli.AvionaSession", lambda _cwd: _Session())
    monkeypatch.setattr(sys, "stdin", type("stdin", (), {"isatty": lambda: True})())
    assert main(["--yes"]) == 0
    assert captured.get("mode") == "auto"


def test_main_bare_invocation_starts_repl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bare aviona checks key locally (no probe) and enters the REPL."""
    monkeypatch.setattr(
        "aviona.cli.ensure_slm_api_key_configured",
        lambda: None,
    )
    monkeypatch.setattr("aviona.cli.load_aviona_env", lambda _cwd=None: None)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        "aviona.cli.run_repl",
        lambda _session, debug=False: 0,
    )
    monkeypatch.setattr("aviona.cli.AvionaSession", lambda _cwd: object())
    code = main([])
    assert code == 0

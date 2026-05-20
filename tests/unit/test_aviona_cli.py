"""Aviona CLI unit tests — no network, no API keys."""

from __future__ import annotations

import argparse

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


def test_main_doctor_stub_exits_zero(capsys) -> None:
    """doctor subcommand runs the AVIONA-1 stub without error."""
    code = main(["doctor"])
    assert code == 0
    assert "doctor" in capsys.readouterr().out.lower()


def test_main_bare_invocation_starts_repl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bare aviona probes once and enters the REPL."""
    monkeypatch.setattr(
        "aviona.cli.validate_slm_api_key",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr("aviona.cli.run_repl", lambda _session: 0)
    monkeypatch.setattr("aviona.cli.AvionaSession", lambda _cwd: object())
    code = main([])
    assert code == 0

"""Aviona doctor CLI unit tests — mocked probe, no real API."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aviona.cli import main
from aviona.doctor import run_doctor
from framework.orchestration.session import ProbeFailedError, ProbeResult


def test_doctor_ok_exits_zero_and_prints_provider(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked successful probe prints provider/model and exits 0."""
    monkeypatch.setattr("aviona.doctor.active_provider_name", lambda: "deepseek")
    monkeypatch.setattr("aviona.doctor.resolve_profile_name", lambda _role: "deepseek-v4-flash")
    monkeypatch.setattr(
        "aviona.doctor.load_profile",
        lambda _name: MagicMock(model_id="deepseek-v4-flash"),
    )
    monkeypatch.setattr(
        "aviona.doctor.api_key_env_var_for_active_provider",
        lambda: "DEEPSEEK_API_KEY",
    )
    monkeypatch.setattr(
        "aviona.doctor.validate_slm_api_key",
        lambda *args, **kwargs: ProbeResult(ok=True, attempts=1),
    )

    code = run_doctor()
    out = capsys.readouterr().out
    assert code == 0
    assert "provider: deepseek" in out
    assert "model: deepseek-v4-flash" in out
    assert "probe: ok" in out


def test_doctor_probe_failed_exits_nonzero(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    """ProbeFailedError yields non-zero exit and reason."""
    monkeypatch.setattr("aviona.doctor.active_provider_name", lambda: "deepseek")
    monkeypatch.setattr("aviona.doctor.resolve_profile_name", lambda _role: "x")
    monkeypatch.setattr(
        "aviona.doctor.load_profile",
        lambda _name: MagicMock(model_id="mock-model"),
    )
    monkeypatch.setattr(
        "aviona.doctor.api_key_env_var_for_active_provider",
        lambda: "DEEPSEEK_API_KEY",
    )

    def _fail(*args, **kwargs):
        raise ProbeFailedError(ProbeResult(ok=False, attempts=2, error="http_503"))

    monkeypatch.setattr("aviona.doctor.validate_slm_api_key", _fail)

    code = run_doctor()
    out = capsys.readouterr().out
    assert code == 1
    assert "probe failed" in out
    assert "http_503" in out


def test_doctor_missing_key_clear_message_no_probe(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing/placeholder key prints error without a successful probe."""
    monkeypatch.setattr("aviona.doctor.active_provider_name", lambda: "deepseek")
    monkeypatch.setattr("aviona.doctor.resolve_profile_name", lambda _role: "x")
    monkeypatch.setattr(
        "aviona.doctor.load_profile",
        lambda _name: MagicMock(model_id="mock-model"),
    )
    monkeypatch.setattr(
        "aviona.doctor.api_key_env_var_for_active_provider",
        lambda: "DEEPSEEK_API_KEY",
    )
    probe_called = False

    def _missing(*args, **kwargs):
        nonlocal probe_called
        probe_called = True
        raise RuntimeError("DEEPSEEK_API_KEY is not set. Add it to .env before running e2e tests.")

    monkeypatch.setattr("aviona.doctor.validate_slm_api_key", _missing)

    code = run_doctor()
    out = capsys.readouterr().out
    assert code == 1
    assert "DEEPSEEK_API_KEY" in out
    assert probe_called


def test_cli_doctor_subcommand_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``aviona doctor`` calls run_doctor without starting REPL."""
    monkeypatch.setattr("aviona.cli.load_aviona_env", lambda _cwd=None: None)
    monkeypatch.setattr("aviona.cli.run_doctor", lambda: 0)
    monkeypatch.setattr(
        "aviona.cli.run_repl",
        lambda _s, debug=False: (_ for _ in ()).throw(AssertionError("no repl")),
    )
    assert main(["doctor"]) == 0

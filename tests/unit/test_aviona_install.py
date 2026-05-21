"""Windows install script gate tests — no API calls."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from aviona import __version__

REPO = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO / "scripts" / "install-aviona.ps1"
INIT_PY = REPO / "src" / "aviona" / "__init__.py"
AVIONA_EXE = REPO / ".venv" / "Scripts" / "aviona.exe"
PYTHON_EXE = REPO / ".venv" / "Scripts" / "python.exe"


def test_install_script_exists_and_supports_dry_run() -> None:
    """Install script exposes -DryRun for the V2-9 structural gate."""
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$DryRun" in text
    assert "Get-CorruptDistInfo" in text
    assert "Stop-AvionaProcesses" in text
    assert "Test-AvionaVersionParity" in text


def test_expected_version_matches_pyproject() -> None:
    """Package __version__ matches pyproject.toml for install parity checks."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None
    assert match.group(1) == __version__
    init_match = re.search(
        r'__version__ = "([^"]+)"',
        INIT_PY.read_text(encoding="utf-8"),
    )
    assert init_match is not None
    assert init_match.group(1) == __version__


@pytest.mark.skipif(sys.platform != "win32", reason="install-aviona.ps1 is Windows-only")
def test_install_script_dry_run_exits_zero() -> None:
    """Dry-run validates venv wiring and package/CLI version parity without pip."""
    if not PYTHON_EXE.is_file():
        pytest.skip("venv missing; run scripts/install-aviona.ps1 first")
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSTALL_SCRIPT),
            "-DryRun",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Dry-run OK" in proc.stdout
    assert __version__ in proc.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="install-aviona.ps1 is Windows-only")
def test_aviona_cli_version_matches_package() -> None:
    """CLI --version reports the same version as import aviona."""
    if not AVIONA_EXE.is_file():
        pytest.skip("aviona.exe missing; run scripts/install-aviona.ps1 first")
    proc = subprocess.run(
        [str(AVIONA_EXE), "--version"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert __version__ in proc.stdout

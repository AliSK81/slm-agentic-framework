"""E2E REPL matrix tests — AV3-4, CI-optional (@pytest.mark.e2e).

Each live-gate case from scripts/live_gate.py becomes one pytest test.
Excluded from default CI by ``pytest -m "not e2e"``.
Invoked via ``scripts/test-aviona.ps1 -Live``.
"""

from __future__ import annotations

import re
import runpy
import subprocess
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_AVIONA_EXE = _REPO / ".venv" / "Scripts" / "aviona.exe"
_DEFAULT_WORKSPACE = Path(r"D:\thesis\aviona-test")
_FALLBACK_WORKSPACE = _REPO / "tests" / "fixtures" / "sample_repo"


def _live_globals() -> dict[str, Any]:
    return runpy.run_path(str(_REPO / "scripts" / "live_gate.py"))


_LG = _live_globals()
LIVE_MATRIX = _LG["LIVE_MATRIX"]
_check_case = _LG["_check_case"]
_parse_runtime_facts = _LG["_parse_runtime_facts"]


def _workspace() -> Path:
    if _DEFAULT_WORKSPACE.is_dir():
        return _DEFAULT_WORKSPACE
    if _FALLBACK_WORKSPACE.is_dir():
        return _FALLBACK_WORKSPACE
    pytest.skip(f"workspace not found: {_DEFAULT_WORKSPACE}")


def _aviona_exe() -> Path:
    if _AVIONA_EXE.is_file():
        return _AVIONA_EXE
    pytest.skip(f"aviona not found at {_AVIONA_EXE}")


def _collect_debug_trace(prompt: str, *, workspace: Path, aviona_exe: Path) -> str:
    """Re-run prompt with --debug; return debug log content (best-effort)."""
    try:
        proc = subprocess.run(
            [str(aviona_exe), "--debug", "--mode", "auto"],
            input=f"{prompt}\n/exit\n",
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        output = proc.stdout + proc.stderr
        match = re.search(r"Logging to:\s*(.+)", output)
        if match:
            log_path = Path(match.group(1).strip())
            if log_path.is_file():
                return log_path.read_text(encoding="utf-8", errors="replace")
        return output
    except Exception as exc:
        return f"(debug trace unavailable: {exc})"


@pytest.mark.e2e
@pytest.mark.parametrize("case", LIVE_MATRIX, ids=[c.case_id for c in LIVE_MATRIX])
def test_aviona_repl_case(case: Any, require_api_key: str) -> None:
    """Drive aviona subprocess for one AV3-3 live matrix case."""
    _ = require_api_key
    workspace = _workspace()
    aviona_exe = _aviona_exe()
    provider, model = _parse_runtime_facts(workspace)

    try:
        _check_case(
            case,
            workspace=workspace,
            aviona_exe=aviona_exe,
            provider=provider,
            model=model,
            timeout=300,
        )
    except AssertionError as exc:
        trace = _collect_debug_trace(case.prompt, workspace=workspace, aviona_exe=aviona_exe)
        raise AssertionError(f"{exc}\n\n--- debug trace ---\n{trace}") from None

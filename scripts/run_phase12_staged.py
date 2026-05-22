"""Phase 12 staged gate: session e2e first, HumanEval only if session passes."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from framework.runtime_dirs import logs_dir

_LOG_DIR = logs_dir()
_PY = _ROOT / ".venv" / "Scripts" / "python.exe"


def _run_stage(name: str, stamp: str, pytest_args: list[str]) -> int:
    """Run pytest; capture combined stdout/stderr to logs."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    stage_log = _LOG_DIR / f"phase12_staged_{stamp}.{name}.log"
    master_log = _LOG_DIR / f"phase12_staged_{stamp}.log"
    cmd = [str(_PY), "-m", "pytest", *pytest_args]
    with stage_log.open("w", encoding="utf-8") as out:
        proc = subprocess.run(
            cmd,
            cwd=_ROOT,
            stdout=out,
            stderr=subprocess.STDOUT,
            text=True,
        )
    line = f"[{datetime.now(UTC).isoformat()}] {name} exit={proc.returncode}\n"
    with master_log.open("a", encoding="utf-8") as master:
        master.write(line)
    print(line.strip())
    return proc.returncode


def main() -> int:
    """Run ROADMAP Phase 12 gate in two stages to save API cost on failure."""
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    print(f"Phase 12 staged run — logs in {_LOG_DIR / f'phase12_staged_{stamp}.*'}")

    session_code = _run_stage(
        "session",
        stamp,
        ["tests/e2e/test_full_session.py", "-m", "e2e", "-v", "--tb=short"],
    )
    if session_code != 0:
        print("STOP: session e2e failed — HumanEval skipped to save API cost.")
        return session_code

    print("Session e2e passed — starting HumanEval benchmarks.")
    return _run_stage(
        "humaneval",
        stamp,
        ["tests/e2e/test_humaneval_sample.py", "-m", "e2e", "-v", "--tb=short"],
    )


if __name__ == "__main__":
    raise SystemExit(main())

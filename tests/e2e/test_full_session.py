"""Full session end-to-end tests (real OpenRouter API)."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.memory.stores import MemoryStores
from framework.orchestration.session import run_full_session

TASK_1 = {
    "goal": "Write a Python function add(a, b) that returns a + b.",
    "constraints": ["Must be named exactly 'add'", "Must handle integers and floats"],
    "test_code": "assert add(1, 2) == 3\nassert add(1.5, 2.5) == 4.0",
}

TASK_2 = {
    "goal": "Fix the bug in the provided function: def multiply(a, b): return a - b",
    "constraints": ["Must not change the function name", "Fix only the operator"],
    "test_code": "assert multiply(3, 4) == 12",
}

TASK_3 = {
    "goal": "Write a Python function is_palindrome(s) that returns True if s is a palindrome.",
    "constraints": ["Case-insensitive", "Ignore spaces"],
    "test_code": (
        "assert is_palindrome('racecar')\n"
        "assert is_palindrome('Race Car')\n"
        "assert not is_palindrome('hello')"
    ),
}


@pytest.fixture
def e2e_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.mark.e2e
def test_full_session_task_1(
    require_api_key: str,
    e2e_workspace: Path,
    tmp_path: Path,
) -> None:
    """Session reaches DONE. TestResult.passed=True. Decision Log has entries."""
    _ = require_api_key
    memory = MemoryStores.sqlite(tmp_path / "t1.db")
    result = run_full_session(
        TASK_1["goal"],
        TASK_1["constraints"],
        TASK_1["test_code"],
        e2e_workspace,
        memory=memory,
        max_steps=12,
        checkpoint_dir=tmp_path / "checkpoints",
    )
    assert result.decision_count > 0
    assert result.test_passed
    assert result.outcome == "solved"


@pytest.mark.e2e
def test_full_session_task_2(
    require_api_key: str,
    e2e_workspace: Path,
    tmp_path: Path,
) -> None:
    """Session reaches DONE. Executor correctly fixes the bug."""
    _ = require_api_key
    (e2e_workspace / "solution.py").write_text(
        "def multiply(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    memory = MemoryStores.sqlite(tmp_path / "t2.db")
    result = run_full_session(
        TASK_2["goal"],
        TASK_2["constraints"],
        TASK_2["test_code"],
        e2e_workspace,
        memory=memory,
        max_steps=12,
        checkpoint_dir=tmp_path / "checkpoints",
    )
    assert result.test_passed
    assert result.outcome == "solved"
    content = (e2e_workspace / "solution.py").read_text(encoding="utf-8")
    assert "*" in content or "+" in content


@pytest.mark.e2e
def test_full_session_task_3(
    require_api_key: str,
    e2e_workspace: Path,
    tmp_path: Path,
) -> None:
    """Session reaches DONE. Generated function passes all 3 test assertions."""
    _ = require_api_key
    memory = MemoryStores.sqlite(tmp_path / "t3.db")
    result = run_full_session(
        TASK_3["goal"],
        TASK_3["constraints"],
        TASK_3["test_code"],
        e2e_workspace,
        memory=memory,
        max_steps=12,
        checkpoint_dir=tmp_path / "checkpoints",
    )
    assert result.test_passed
    assert result.outcome == "solved"


@pytest.mark.e2e
def test_decision_log_has_entries_after_session(
    require_api_key: str,
    e2e_workspace: Path,
    tmp_path: Path,
) -> None:
    """After any completed session, Decision Log is non-empty."""
    _ = require_api_key
    memory = MemoryStores.sqlite(tmp_path / "t4.db")
    result = run_full_session(
        TASK_1["goal"],
        TASK_1["constraints"],
        TASK_1["test_code"],
        e2e_workspace,
        memory=memory,
        max_steps=8,
    )
    assert result.decision_count > 0


@pytest.mark.e2e
def test_state_store_has_snapshots_after_session(
    require_api_key: str,
    e2e_workspace: Path,
    tmp_path: Path,
) -> None:
    """State Store has at least 2 snapshots (initial + final)."""
    _ = require_api_key
    memory = MemoryStores.sqlite(tmp_path / "t5.db")
    result = run_full_session(
        TASK_1["goal"],
        TASK_1["constraints"],
        TASK_1["test_code"],
        e2e_workspace,
        memory=memory,
        max_steps=8,
    )
    assert result.state_snapshot_count >= 2


@pytest.mark.e2e
def test_checkpoint_exists_after_session(
    require_api_key: str,
    e2e_workspace: Path,
    tmp_path: Path,
) -> None:
    """Checkpoint file exists in CHECKPOINT_DIR after session."""
    _ = require_api_key
    ckpt_dir = tmp_path / "checkpoints"
    memory = MemoryStores.sqlite(tmp_path / "t6.db")
    result = run_full_session(
        TASK_1["goal"],
        TASK_1["constraints"],
        TASK_1["test_code"],
        e2e_workspace,
        memory=memory,
        max_steps=8,
        checkpoint_dir=ckpt_dir,
    )
    assert result.checkpoint_path is not None
    assert Path(result.checkpoint_path).is_file()

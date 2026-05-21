"""AV3-2: permission mode banner, confirm UX, inspect-run without prompt."""

from __future__ import annotations

from pathlib import Path

import pytest

from aviona.permissions import (
    PermissionAction,
    PermissionGate,
    permission_mode_banner,
)
from aviona.repl import run_repl
from aviona.repl import ScriptedReader
from aviona.session import AvionaSession, TurnResult


def test_permission_mode_banner_describes_each_mode() -> None:
    """REPL banner text documents plan/default/auto behavior."""
    assert "read-only" in permission_mode_banner("plan").lower()
    assert "[y/n]" in permission_mode_banner("default").lower()
    assert "without prompts" in permission_mode_banner("auto").lower()


def test_default_mode_asks_for_side_effect_shell() -> None:
    """Default mode prompts before non-inspect side-effecting shell."""
    prompts: list[str] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return True

    gate = PermissionGate("default", allowlist=["python"], confirm=confirm)
    action = PermissionAction(kind="shell", detail="python run.py")
    assert gate.check(action) == "ask"
    assert gate.ensure(action)
    assert len(prompts) == 1
    assert "[y/N]" in prompts[0]
    assert "run.py" in prompts[0]


def test_default_mode_denies_shell_when_user_declines() -> None:
    """Rejected confirm blocks the shell action."""
    gate = PermissionGate("default", confirm=lambda _p: False)
    assert not gate.ensure(PermissionAction(kind="shell", detail="python run.py"))


def test_default_mode_allows_inspect_run_without_prompt() -> None:
    """FI-6 inspect-run commands skip confirm in default mode."""
    prompts: list[str] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return True

    gate = PermissionGate("default", confirm=confirm)
    for cmd in (
        "pytest tests/",
        "python -m pytest tests/unit",
        'python -c "print(1)"',
    ):
        assert gate.check(PermissionAction(kind="shell", detail=cmd)) == "allow"
        assert gate.ensure(PermissionAction(kind="shell", detail=cmd))
    assert prompts == []


def test_auto_mode_never_prompts_for_shell() -> None:
    """Auto mode allows side-effecting shell without calling confirm."""
    called = False

    def confirm(_prompt: str) -> bool:
        nonlocal called
        called = True
        return False

    gate = PermissionGate("auto", allowlist=["pytest"], confirm=confirm)
    assert gate.ensure(PermissionAction(kind="shell", detail="pytest tests/"))
    assert not called


def test_repl_startup_shows_permission_banner(tmp_path: Path) -> None:
    """Session start prints the permission mode banner."""
    workspace = tmp_path / "repl-banner"
    workspace.mkdir()
    session = AvionaSession(workspace)
    lines: list[str] = []

    run_repl(
        session,
        reader=ScriptedReader(["/exit"]),
        writer=lines.append,
        run_turn=lambda _t: TurnResult(status="ok", outcome="solved", session_id="s"),
    )
    joined = "\n".join(lines)
    assert "Permission mode:" in joined
    assert "default" in joined.lower()

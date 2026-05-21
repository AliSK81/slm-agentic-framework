"""AV3-1: Aviona consumes framework ICP; no local turn-type/budget heuristics."""

from __future__ import annotations

import inspect
from pathlib import Path
import pytest

import aviona.runtime as aviona_runtime
from aviona.budgets import TURN_CYCLE_CAPS, max_cycles_for_turn_type
from aviona.contract import TurnContractResult, TurnFileObs
from aviona.render import render_turn_detail
from aviona.session import AvionaSession
from framework.control.interactive import load_interactive_budgets
from framework.orchestration.session import SessionOutcome


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def test_infer_interactive_max_steps_deleted() -> None:
    """Aviona must not expose goal-regex step inference (A04/F03)."""
    assert not hasattr(aviona_runtime, "infer_interactive_max_steps")
    source = inspect.getsource(aviona_runtime)
    assert "infer_interactive_max_steps" not in source


def test_turn_cycle_caps_match_framework_yaml() -> None:
    """Display/contract caps mirror configs/models.yaml interactive.budgets."""
    budgets = load_interactive_budgets()
    assert max_cycles_for_turn_type("answer") == budgets["answer"]
    assert max_cycles_for_turn_type("inspect") == budgets["inspect"]
    assert max_cycles_for_turn_type("edit") == budgets["edit"]
    assert max_cycles_for_turn_type("build") == budgets["build"]
    assert TURN_CYCLE_CAPS["inspect"] == 4


def test_render_turn_detail_shows_verbatim_user_message() -> None:
    """Passed contract renders framework user_message without mutation."""
    outcome = SessionOutcome(
        session_id="s",
        user_message="  Exact reply.  ",
        outcome="solved",
    )
    detail = render_turn_detail(outcome, TurnContractResult(passed=True))
    assert detail == "Exact reply."


def test_render_turn_detail_unresolvable_prefixes_reason() -> None:
    """Failed contract renders honest ``! reason`` line."""
    outcome = SessionOutcome(session_id="s", outcome="unresolvable", error="missing user_message")
    contract = TurnContractResult(passed=False, failure_reason="missing user_message")
    detail = render_turn_detail(outcome, contract)
    assert detail == "! missing user_message"


def test_aviona_run_turn_does_not_pass_max_steps_to_framework(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session delegates budgets to framework; no caller max_steps kwarg."""
    session = AvionaSession(workspace)
    captured: dict[str, object] = {}

    def _fake_framework_run_turn(*args: object, **kwargs: object) -> SessionOutcome:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SessionOutcome(
            session_id=session._session_id,
            user_message="ok",
            outcome="solved",
            step_count=1,
        )

    monkeypatch.setattr(
        "aviona.session.framework_run_turn",
        _fake_framework_run_turn,
    )
    monkeypatch.setattr(
        "aviona.session.verify_turn",
        lambda *a, **k: TurnContractResult(passed=True),
    )
    monkeypatch.setattr(
        "aviona.session.verify_turn_budget",
        lambda *a, **k: TurnContractResult(passed=True),
    )
    monkeypatch.setattr(
        "aviona.session.declared_turn_type",
        lambda *a, **k: "answer",
    )
    monkeypatch.setattr(
        "aviona.session.changed_paths_for_turn",
        lambda *a, **k: [],
    )

    result = session.run_turn("hi")

    assert result.detail == "ok"
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert "max_steps" not in kwargs
    sig = inspect.signature(AvionaSession.run_turn)
    assert "max_steps" not in sig.parameters

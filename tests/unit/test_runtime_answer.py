"""Runtime self-knowledge via anchor facts (V2-7)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aviona.runtime import (
    infer_interactive_max_steps,
    runtime_anchor_segment,
    runtime_answer_constraint,
)
from aviona.session import AvionaSession
from framework.control.ablation import AblationSettings
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import MemoryStores
from framework.orchestration.session import ProbeResult, run_turn
from framework.slm.client import ModelProfile, SLMResponse


class MockSLMClient:
    """Queue-based SLM stub for runtime answer tests."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.profile = ModelProfile(
            model_id="deepseek/deepseek-v4-flash",
            context_limit=4096,
            effective_context=4096,
            max_working_memory_tokens=650,
            tool_output_caps={},
            skill_budget_tokens=120,
            timeout_by_role={"planner": 60, "executor": 75},
        )
        self.call_count = 0

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        _ = json_mode
        self.call_count += 1
        if not self._responses:
            return SLMResponse(error="empty_queue", model="mock")
        return SLMResponse(
            content=self._responses.pop(0),
            model="mock",
            tokens_used=1,
            elapsed_ms=1,
        )

    def close(self) -> None:
        return None


def _terminate(message: str, turn_type: str = "answer") -> str:
    return json.dumps(
        {
            "kind": "terminate",
            "rationale": "Answer from runtime anchor facts.",
            "payload": {"user_message": message, "turn_type": turn_type},
            "references": [],
        }
    )


def _mock_profiles(monkeypatch: pytest.MonkeyPatch, model_id: str) -> None:
    profile = MagicMock()
    profile.model_id = model_id

    monkeypatch.setattr("framework.slm.config.load_profile", lambda _name: profile)
    monkeypatch.setattr("framework.slm.config.active_provider_name", lambda: "deepseek")
    monkeypatch.setattr("framework.slm.registry.resolve_profile_name", lambda role: role)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores(SQLiteBackend(tmp_path / "runtime.db"))


def test_infer_interactive_max_steps_by_goal_shape() -> None:
    """Inspect-style goals get a tight cycle ceiling; edits get more room."""
    assert infer_interactive_max_steps("hi") == 1
    assert infer_interactive_max_steps("tell me what is your llm model?") == 1
    assert infer_interactive_max_steps("list files in this dir") == 3
    assert infer_interactive_max_steps('create bar.txt with "debug-smoke"') == 6
    assert (
        infer_interactive_max_steps(
            'run this code with input "ali" and show me the result'
        )
        == 6
    )


def test_runtime_anchor_segment_includes_model_version_and_cwd(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime anchor carries product identity facts for self-questions."""
    model_id = "deepseek/deepseek-v4-flash"
    _mock_profiles(monkeypatch, model_id)

    segment = runtime_anchor_segment(cwd=workspace)

    assert "product=aviona" in segment
    assert "provider=deepseek" in segment
    assert f"model={model_id}" in segment
    assert "version=" in segment
    assert f"cwd={workspace.resolve()}" in segment


def test_runtime_answer_constraint_mentions_anchor_facts() -> None:
    """Self-knowledge constraint directs the agent to runtime facts, not repo reads."""
    text = runtime_answer_constraint()
    assert text.startswith("[AVIONA] Self/meta")
    assert "runtime:" in text
    assert "turn_type:answer" in text
    assert "do not read" in text.lower()


def test_aviona_session_anchor_includes_runtime_facts(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session history anchor embeds runtime facts and the self-knowledge constraint."""
    model_id = "deepseek/deepseek-v4-flash"
    _mock_profiles(monkeypatch, model_id)

    session = AvionaSession(workspace)
    constraints = session._build_turn_constraints(goal="what is your model?")

    anchor = session._history[0].text
    assert f"model={model_id}" in anchor
    assert runtime_answer_constraint() in constraints
    assert any("Turn types:" in c for c in constraints)


def test_what_model_turn_one_cycle_read_only(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mocked agent answers model question from anchor facts in one read-only cycle."""
    model_id = "deepseek/deepseek-v4-flash"
    _mock_profiles(monkeypatch, model_id)
    executor = MockSLMClient(
        [_terminate(f"I am running model {model_id}.", "answer")]
    )
    planner = MockSLMClient([])

    monkeypatch.setattr(
        "framework.orchestration.session.client_for_role",
        lambda role: planner if role == "planner" else executor,
    )
    monkeypatch.setattr(
        "framework.orchestration.session.validate_slm_api_key",
        lambda *args, **kwargs: ProbeResult(ok=True, attempts=1),
    )

    constraints = [
        runtime_anchor_segment(cwd=workspace),
        runtime_answer_constraint(),
    ]
    outcome = run_turn(
        "what model are you?",
        constraints,
        workspace,
        memory=memory,
        session_id="sess-runtime",
        probe=False,
        max_steps=1,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=True, error_control=False),
    )

    assert outcome.llm_calls == 1
    assert executor.call_count == 1
    assert model_id in outcome.user_message
    assert not list(workspace.rglob("*"))


def test_model_question_after_prior_turn_succeeds(
    workspace: Path,
    memory: MemoryStores,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second turn must not fail SELF_CHECK contradiction vs prior user_message."""
    model_id = "deepseek/deepseek-v4-flash"
    _mock_profiles(monkeypatch, model_id)
    executor = MockSLMClient(
        [
            _terminate("ali ali", "answer"),
            _terminate(f"My LLM model is {model_id}.", "answer"),
        ]
    )
    planner = MockSLMClient([])

    monkeypatch.setattr(
        "framework.orchestration.session.client_for_role",
        lambda role: planner if role == "planner" else executor,
    )
    monkeypatch.setattr(
        "framework.orchestration.session.validate_slm_api_key",
        lambda *args, **kwargs: ProbeResult(ok=True, attempts=1),
    )

    constraints = [
        runtime_anchor_segment(cwd=workspace),
        runtime_answer_constraint(),
    ]
    session_id = "sess-two-turn"
    first = run_turn(
        'just say "ali ali"',
        constraints,
        workspace,
        memory=memory,
        session_id=session_id,
        probe=False,
        max_steps=1,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=True, error_control=False),
    )
    second = run_turn(
        "tell me what is your llm model?",
        constraints,
        workspace,
        memory=memory,
        session_id=session_id,
        probe=False,
        max_steps=1,
        interactive_read_only=True,
        ablation=AblationSettings(memory=False, control=True, error_control=False),
    )

    assert first.user_message == "ali ali"
    assert model_id in second.user_message
    assert second.llm_calls == 1
    assert executor.call_count == 2

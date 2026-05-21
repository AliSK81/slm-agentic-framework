"""FI-1: agent-declared turn_type binds framework budget and permissions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from framework.control.interactive import (
    bind_interactive_turn,
    clear_interactive_config_cache,
    declaring_interactive_turn_state,
    load_interactive_budgets,
)
from framework.control.self_check import self_check
from framework.memory.backend import SQLiteBackend
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord
from framework.orchestration.session import (
    _apply_interactive_turn_binding,
    _interactive_initial_state,
    _run_interactive_executor_turn,
)
from framework.slm.client import ModelProfile, SLMResponse


class _QueueSLM:
    """Minimal SLM stub returning queued JSON decision strings."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.call_count = 0
        self.profile = ModelProfile(
            model_id="mock",
            context_limit=4096,
            effective_context=4096,
            max_working_memory_tokens=650,
            tool_output_caps={},
            skill_budget_tokens=120,
            timeout_by_role={"planner": 60, "executor": 75},
        )

    def call(
        self,
        messages: list[dict[str, str]],
        role: str,
        json_mode: bool = True,
    ) -> SLMResponse:
        _ = messages, role, json_mode
        self.call_count += 1
        if not self._responses:
            return SLMResponse(error="empty", model="mock")
        return SLMResponse(
            content=self._responses.pop(0),
            model="mock",
            tokens_used=1,
            elapsed_ms=1,
        )

    def close(self) -> None:
        return None


def _terminate_json(message: str, turn_type: str) -> str:
    return json.dumps(
        {
            "kind": "terminate",
            "rationale": "done",
            "payload": {"user_message": message, "turn_type": turn_type},
            "references": [],
        }
    )


def _tool_json(tool: str, turn_type: str, **extra: object) -> str:
    payload: dict[str, object] = {"tool": tool, "turn_type": turn_type, **extra}
    return json.dumps(
        {
            "kind": "tool_call",
            "rationale": "inspect workspace",
            "payload": payload,
            "references": [],
        }
    )


def test_load_interactive_budgets_from_models_yaml() -> None:
    """Framework budget map matches ROADMAP FI-1 defaults."""
    clear_interactive_config_cache()
    budgets = load_interactive_budgets()
    assert budgets == {"answer": 1, "inspect": 4, "edit": 6, "run": 4, "build": 15}


def test_bind_inspect_sets_budget_four_and_read_only() -> None:
    """declares inspect → budget=4, read_only=True."""
    clear_interactive_config_cache()
    bound = bind_interactive_turn("inspect")
    assert bound.max_steps == 4
    assert bound.read_only is True
    assert bound.declared_type == "inspect"
    assert bound.bound is True


def test_bind_edit_allows_writes_budget_six() -> None:
    """declares edit → write tools allowed (read_only=False), budget=6."""
    clear_interactive_config_cache()
    bound = bind_interactive_turn("edit")
    assert bound.max_steps == 6
    assert bound.read_only is False


def test_declaring_state_starts_read_only_single_step() -> None:
    """Before bind, declaring phase uses one cycle and read_only=True."""
    declaring = declaring_interactive_turn_state()
    assert declaring.max_steps == 1
    assert declaring.read_only is True
    assert declaring.bound is False


def test_self_check_turn_type_required_when_missing_on_cycle_one(
    tmp_path: Path,
) -> None:
    """missing turn_type on cycle 1 → self_check issue turn_type_required."""
    memory = MemoryStores(SQLiteBackend(tmp_path / "sc.db"))
    session_id = "sess-tt"
    proposal = DecisionEntry(
        session_id=session_id,
        decision_id="d-1",
        step_index=0,
        by_agent="executor",
        kind="terminate",
        payload={"user_message": "hello"},
        rationale="answer user",
        references=[],
        self_check=SelfCheckRecord(verdict="fail", issues=[]),
        timestamp=datetime.now(UTC),
    )
    record = self_check(proposal, memory, session_id, require_turn_type=True)
    assert record.verdict == "fail"
    kinds = [issue.kind for issue in record.issues]
    assert "turn_type_required" in kinds


def test_apply_binding_updates_executor_read_only(tmp_path: Path) -> None:
    """Binding inspect on state sets executor interactive_read_only True."""
    from framework.control.ablation import AblationSettings
    from framework.memory.stores import MemoryStores as MS
    from framework.orchestration.session import _build_agents

    memory = MS.sqlite(tmp_path / "bind.db")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _, executor, _, _ = _build_agents(
        memory,
        workspace,
        AblationSettings(),
        interactive_read_only=False,
    )
    state = _interactive_initial_state("s1", "list files", [], max_retries=2)
    decision = DecisionEntry(
        session_id="s1",
        decision_id="d-x",
        step_index=0,
        by_agent="executor",
        kind="tool_call",
        payload={"tool": "list_dir", "path": ".", "turn_type": "inspect"},
        rationale="list",
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )
    assert _apply_interactive_turn_binding(state, decision, executor) is True
    assert state["interactive_turn_bound"] is True
    assert int(state["max_steps"]) == 4
    assert executor.interactive_read_only is True


def test_apply_binding_edit_clears_read_only(tmp_path: Path) -> None:
    """Binding edit allows writes on the executor."""
    from framework.control.ablation import AblationSettings
    from framework.memory.stores import MemoryStores as MS
    from framework.orchestration.session import _build_agents

    memory = MS.sqlite(tmp_path / "edit.db")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _, executor, _, _ = _build_agents(
        memory,
        workspace,
        AblationSettings(),
        interactive_read_only=True,
    )
    state = _interactive_initial_state("s2", "create foo.txt", [], max_retries=2)
    decision = DecisionEntry(
        session_id="s2",
        decision_id="d-y",
        step_index=0,
        by_agent="executor",
        kind="code_edit",
        payload={"file_path": "foo.txt", "new_string": "x", "turn_type": "edit"},
        rationale="create",
        references=[],
        self_check=SelfCheckRecord(verdict="pass", issues=[]),
        timestamp=datetime.now(UTC),
    )
    assert _apply_interactive_turn_binding(state, decision, executor) is True
    assert int(state["max_steps"]) == 6
    assert executor.interactive_read_only is False


def test_interactive_turn_uses_bound_inspect_budget(tmp_path: Path) -> None:
    """Full interactive turn respects inspect budget from declared turn_type."""
    from framework.control.ablation import AblationSettings
    from framework.memory.stores import MemoryStores as MS
    from framework.orchestration.session import _build_agents
    from framework.orchestration.verify import NoOpVerifier

    memory = MS.sqlite(tmp_path / "turn.db")
    session_id = "sess-inspect"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    slm = _QueueSLM(
        [
            _tool_json("list_dir", "inspect", path="."),
            _terminate_json("Listed.", "inspect"),
        ]
    )
    planner, executor, _, _ = _build_agents(
        memory,
        workspace,
        AblationSettings(memory=True, control=True, error_control=True),
        interactive_read_only=True,
    )
    executor._cycle._slm = slm  # noqa: SLF001
    planner._cycle._slm = _QueueSLM([_terminate_json("unused", "answer")])

    outcome = _run_interactive_executor_turn(
        goal="list files in this dir",
        constraints=[],
        workspace=workspace,
        memory=memory,
        executor=executor,
        verifier=NoOpVerifier(),
        session_id=session_id,
        max_retries=2,
    )
    assert outcome.outcome == "solved"
    assert outcome.step_count <= 4


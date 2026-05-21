"""FI-3: identical list_dir is rejected; terminate completes the turn."""

from __future__ import annotations

import json
from pathlib import Path

from framework.control.ablation import AblationSettings
from framework.memory.stores import MemoryStores
from framework.orchestration.session import _run_interactive_executor_turn
from framework.orchestration.verify import NoOpVerifier
from framework.slm.client import ModelProfile, SLMResponse


class _QueueSLM:
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
            timeout_by_role={"executor": 75},
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


def _list_dir(turn_type: str = "inspect") -> str:
    return json.dumps(
        {
            "kind": "tool_call",
            "rationale": "list",
            "payload": {"tool": "list_dir", "path": ".", "turn_type": turn_type},
            "references": [],
        }
    )


def _terminate(msg: str = "Listed.", turn_type: str = "inspect") -> str:
    return json.dumps(
        {
            "kind": "terminate",
            "rationale": "done",
            "payload": {"user_message": msg, "turn_type": turn_type},
            "references": [],
        }
    )


def test_list_dir_repeat_blocked_then_terminate(tmp_path: Path) -> None:
    """Second identical list_dir fails self_check; terminate succeeds without synthesis."""
    from framework.orchestration.session import _build_agents

    memory = MemoryStores.sqlite(tmp_path / "icp.db")
    session_id = "sess-icp"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    slm = _QueueSLM(
        [
            _list_dir(),
            _list_dir(),
            _terminate(),
        ]
    )
    _, executor, _, _ = _build_agents(
        memory,
        workspace,
        AblationSettings(memory=True, control=True, error_control=True),
        interactive_read_only=True,
    )
    executor._cycle._slm = slm  # noqa: SLF001

    outcome = _run_interactive_executor_turn(
        goal="list files",
        constraints=[],
        workspace=workspace,
        memory=memory,
        executor=executor,
        verifier=NoOpVerifier(),
        session_id=session_id,
        max_retries=3,
    )

    assert outcome.outcome == "solved"
    assert outcome.user_message == "Listed."
    assert slm.call_count == 3, "list_dir, rejected repeat, terminate"
    tool_entries = memory.tool_results.list_for_turn(session_id, 0)
    list_dir_runs = [e for e in tool_entries if e.tool == "list_dir"]
    assert len(list_dir_runs) == 1, "duplicate list_dir must not execute"
    assert "README.md" not in (outcome.user_message or "")

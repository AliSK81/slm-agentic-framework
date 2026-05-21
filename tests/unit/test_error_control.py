"""Error control unit tests — parser, quality, truncation, watchdog, sandbox, checkpoint."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from framework.error_control.parser import parse_decision
from framework.error_control.quality import QualityGate
from framework.error_control.sandbox import safe_execute
from framework.error_control.truncation import truncate
from framework.error_control.watchdog import TimeoutResult, call_with_timeout
from framework.memory.checkpoint import load_latest_checkpoint, save_checkpoint
from framework.memory.stores import DecisionEntry, MemoryStores, SelfCheckRecord, SubTask


class SampleDecision(BaseModel):
    """Minimal decision schema for parser tests."""

    kind: str
    rationale: str


def _self_check() -> SelfCheckRecord:
    return SelfCheckRecord(verdict="pass", issues=[])


def _decision(
    decision_id: str,
    *,
    kind: str = "tool_call",
    payload: dict | None = None,
) -> DecisionEntry:
    return DecisionEntry(
        session_id="sess-1",
        decision_id=decision_id,
        step_index=0,
        by_agent="executor",
        kind=kind,  # type: ignore[arg-type]
        payload=payload or {"x": decision_id},
        rationale="rationale",
        references=[],
        self_check=_self_check(),
        timestamp=datetime.now(UTC),
    )


# --- Parser ---


def test_parser_handles_json_fence() -> None:
    raw = '```json\n{"kind": "plan_step", "rationale": "decompose"}\n```'
    parsed = parse_decision(raw, SampleDecision)
    assert parsed is not None
    assert parsed.kind == "plan_step"


def test_parser_handles_trailing_comma() -> None:
    raw = '{"kind": "tool_call", "rationale": "run",}'
    parsed = parse_decision(raw, SampleDecision)
    assert parsed is not None
    assert parsed.rationale == "run"


def test_parser_handles_single_quoted_keys() -> None:
    raw = """{'kind': 'code_edit', 'rationale': 'patch'}"""
    parsed = parse_decision(raw, SampleDecision)
    assert parsed is not None
    assert parsed.kind == "code_edit"


def test_parser_handles_truncated_json() -> None:
    raw = '{"kind": "handoff", "rationale": "need planner"'
    parsed = parse_decision(raw, SampleDecision)
    assert parsed is not None
    assert parsed.kind == "handoff"


def test_parser_returns_none_on_unrecoverable() -> None:
    parsed = parse_decision("not json at all", SampleDecision)
    assert parsed is None


def test_parser_preserves_escaped_newline_in_rationale() -> None:
    """Repair must not double-escape \\n inside JSON string values."""
    raw = '{"kind": "code_edit", "rationale": "line one\\nline two"}'
    parsed = parse_decision(raw, SampleDecision)
    assert parsed is not None
    assert parsed.rationale == "line one\nline two"


def test_parser_repairs_literal_newline_in_string() -> None:
    """Pattern 8: raw newlines inside JSON strings are escaped before parse."""
    raw = '{"kind": "code_edit", "rationale": "line one\nline two"}'
    parsed = parse_decision(raw, SampleDecision)
    assert parsed is not None
    assert parsed.kind == "code_edit"
    assert parsed.rationale == "line one\nline two"


# --- Quality gate ---


def test_quality_gate_fails_on_empty() -> None:
    gate = QualityGate()
    result = gate.check("", None, [])
    assert not result.passed
    assert result.failure_mode == "empty_response"


def test_quality_gate_fails_on_unparseable() -> None:
    gate = QualityGate()
    result = gate.check("some text", None, [])
    assert not result.passed
    assert result.failure_mode == "unparseable"


def test_quality_gate_detects_loop_at_threshold_3() -> None:
    gate = QualityGate(loop_threshold=3, window=5)
    recent = [
        _decision("d1", kind="tool_call", payload={"tool": "pytest"}),
        _decision("d2", kind="tool_call", payload={"tool": "pytest"}),
        _decision("d3", kind="tool_call", payload={"tool": "pytest"}),
    ]
    result = gate.check("ok", SampleDecision(kind="tool_call", rationale="x"), recent)
    assert not result.passed
    assert result.failure_mode == "loop"


def test_quality_gate_passes_clean_input() -> None:
    gate = QualityGate()
    parsed = SampleDecision(kind="plan_step", rationale="ok")
    result = gate.check('{"kind":"plan_step","rationale":"ok"}', parsed, [])
    assert result.passed


# --- Truncation ---


def test_truncation_asymmetric_formula() -> None:
    """text of 10000 chars, cap 4000 → head=3000, tail=1000."""
    from framework.error_control.truncation import set_caps_profile

    set_caps_profile("default")
    text = "a" * 10000
    out = truncate(text, "pytest_run")
    assert len(out) == 4000
    assert out[:3000] == "a" * 3000
    assert out[3000:] == "a" * 1000


def test_truncation_passthrough_under_cap() -> None:
    text = "short"
    assert truncate(text, "pytest_run") == text


# --- Watchdog ---


def test_watchdog_returns_result_before_timeout() -> None:
    def add(a: int, b: int) -> int:
        return a + b

    result = call_with_timeout(add, {"a": 2, "b": 3}, timeout_s=2)
    assert result == 5


def test_watchdog_returns_timeout_result_on_slow_fn() -> None:
    def slow() -> str:
        time.sleep(2)
        return "done"

    result = call_with_timeout(slow, {}, timeout_s=1)
    assert isinstance(result, TimeoutResult)
    assert result.timed_out


def test_watchdog_never_raises() -> None:
    def boom() -> None:
        raise RuntimeError("fail")

    result = call_with_timeout(boom, {}, timeout_s=2)
    assert isinstance(result, TimeoutResult)
    assert not result.timed_out


# --- Sandbox ---


def test_sandbox_allows_pytest(tmp_path: Path) -> None:
    result = safe_execute("pytest --version", tmp_path, timeout_s=15)
    assert not result.blocked


def test_sandbox_blocks_rm(tmp_path: Path) -> None:
    result = safe_execute("rm -rf /", tmp_path, timeout_s=5)
    assert result.blocked
    assert not result.ok


def test_sandbox_blocks_curl(tmp_path: Path) -> None:
    result = safe_execute("curl http://example.com", tmp_path, timeout_s=5)
    assert result.blocked


# --- Checkpoint ---


@pytest.fixture
def memory(tmp_path: Path) -> MemoryStores:
    return MemoryStores.sqlite(tmp_path / "mem.db")


def test_checkpoint_saves_and_loads(memory: MemoryStores, tmp_path: Path) -> None:
    ckpt_dir = tmp_path / "checkpoints"
    memory.subtasks.register(
        SubTask(
            task_id="t-1",
            parent_session_id="sess-ckpt",
            description="task",
            status="open",
            owner="planner",
        )
    )
    path = save_checkpoint("sess-ckpt", 0, memory, checkpoint_dir=ckpt_dir)
    assert path.exists()
    loaded = load_latest_checkpoint("sess-ckpt", checkpoint_dir=ckpt_dir)
    assert loaded is not None
    assert loaded["session_id"] == "sess-ckpt"
    assert len(loaded["stores"]["subtasks"]) == 1


def test_checkpoint_atomic_write(memory: MemoryStores, tmp_path: Path) -> None:
    """Simulate crash during write (partial .tmp); load still returns prior checkpoint."""
    ckpt_dir = tmp_path / "checkpoints"
    memory.subtasks.register(
        SubTask(
            task_id="t-a",
            parent_session_id="sess-atomic",
            description="first",
            status="open",
            owner="planner",
        )
    )
    save_checkpoint("sess-atomic", 0, memory, checkpoint_dir=ckpt_dir)

    partial = ckpt_dir / "sess-atomic_000001.json.tmp"
    partial.write_text("{ incomplete", encoding="utf-8")

    loaded = load_latest_checkpoint("sess-atomic", checkpoint_dir=ckpt_dir)
    assert loaded is not None
    assert loaded["step_index"] == 0
    assert loaded["stores"]["subtasks"][0]["description"] == "first"

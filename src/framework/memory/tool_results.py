"""Helpers for typed interactive tool-result channel."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from framework.error_control.truncation import truncate
from framework.memory.stores import MemoryStores, ToolResultEntry


def truncation_key_for_tool(tool: str) -> str:
    """Map executor tool names to truncation profile keys."""
    normalized = tool.strip().lower()
    if normalized in ("read_file", "list_dir", "glob", "grep", "write_file", "edit_file"):
        return "read_file"
    if normalized in ("shell", "run_command", "pytest"):
        return "pytest_run"
    if normalized in ("py_compile", "py_compile_check"):
        return "py_compile"
    return "read_file"


def append_tool_result(
    memory: MemoryStores,
    *,
    session_id: str,
    turn_floor: int,
    tool: str,
    path: str,
    output: str,
    ok: bool,
) -> ToolResultEntry:
    """Append a truncated tool result to the session tool-result log."""
    truncated = truncate(output, truncation_key_for_tool(tool))
    entry = ToolResultEntry(
        entry_id=f"tr-{uuid.uuid4().hex[:8]}",
        session_id=session_id,
        turn_floor=turn_floor,
        tool=tool,
        path=path,
        truncated_output=truncated,
        ok=ok,
        timestamp=datetime.now(UTC),
    )
    return memory.tool_results.append(entry)


def recent_turn_recap(
    memory: MemoryStores,
    session_id: str,
    *,
    decision_floor: int,
) -> list[str]:
    """Build short recap lines for anaphora (edited paths this turn)."""
    lines: list[str] = []
    for entry in memory.decisions.list_for_session(session_id)[decision_floor:]:
        if entry.kind != "code_edit":
            continue
        payload = entry.payload or {}
        file_path = str(payload.get("file_path") or payload.get("path") or "").strip()
        if file_path:
            lines.append(f"edited: {file_path}")
    return lines[-5:]

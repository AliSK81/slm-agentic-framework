"""Factual file observations for Aviona turns (no regex NLU)."""

from __future__ import annotations

from pathlib import Path

from aviona.contract import TurnType
from framework.control.models import is_needs_plan_handoff, parse_terminate_payload
from framework.memory.stores import DecisionEntry


def snapshot_files(workspace: Path) -> dict[str, float]:
    """Map workspace-relative file paths to modification times."""
    root = workspace.resolve()
    files: dict[str, float] = {}
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel.startswith(".aviona/"):
            continue
        if "/__pycache__/" in f"/{rel}/" or rel.startswith("__pycache__/"):
            continue
        files[rel] = path.stat().st_mtime
    return files


def changed_files(before: dict[str, float], after: dict[str, float]) -> list[str]:
    """Return paths that were added or modified between snapshots."""
    changed: list[str] = []
    for path, mtime in after.items():
        if path not in before or before[path] != mtime:
            changed.append(path)
    return sorted(changed)


def path_from_payload(payload: dict) -> str | None:
    """Resolve a file path key from a decision payload."""
    sources = [payload]
    for nested_key in ("arguments", "args", "params"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            sources.append(nested)
    for source in sources:
        for key in ("file_path", "filePath", "file", "path"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _tool_name(payload: dict) -> str:
    """Resolve tool name from alternate SLM payload keys."""
    for key in ("tool", "name", "function", "command"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return ""


def collect_tool_paths(
    new_entries: list[DecisionEntry],
) -> tuple[list[str], list[str], list[str]]:
    """Return edited, listed, and read paths from new decision entries."""
    edited: list[str] = []
    listed: list[str] = []
    read_paths: list[str] = []
    for entry in new_entries:
        payload = entry.payload or {}
        if entry.kind == "code_edit":
            path = path_from_payload(payload)
            if path:
                edited.append(path)
        elif entry.kind == "tool_call":
            tool = _tool_name(payload)
            path = path_from_payload(payload) or "."
            if tool in ("write_file", "edit_file"):
                if path:
                    edited.append(path)
            elif tool == "list_dir":
                listed.append(path)
            elif tool == "read_file":
                read_paths.append(path)
    return edited, listed, read_paths


def changed_paths_for_turn(
    before: dict[str, float],
    after: dict[str, float],
    new_entries: list[DecisionEntry],
) -> list[str]:
    """Merge filesystem snapshots with decision-log edit paths."""
    edited, _, _ = collect_tool_paths(new_entries)
    return sorted(set(edited + changed_files(before, after)))


def declared_turn_type(
    new_entries: list[DecisionEntry],
    *,
    file_changes: list[str],
    build_promoted: bool = False,
) -> TurnType:
    """Read agent-declared turn_type; infer inspect/edit when terminate omits it."""
    terminate_type: TurnType | None = None
    for entry in reversed(new_entries):
        if entry.kind == "terminate":
            parsed = parse_terminate_payload(entry.payload)
            terminate_type = parsed.turn_type
            break

    if terminate_type == "answer":
        return "answer"
    if terminate_type in ("inspect", "edit", "build"):
        return terminate_type

    edited, listed, read_paths = collect_tool_paths(new_entries)
    has_code_edit = any(entry.kind == "code_edit" for entry in new_entries)

    if file_changes or has_code_edit or edited:
        return "edit"
    if listed or read_paths:
        return "inspect"
    for entry in reversed(new_entries):
        if build_promoted and is_needs_plan_handoff(entry):
            return "build"
    return "answer"

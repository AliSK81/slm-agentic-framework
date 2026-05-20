"""Detect whether an Aviona turn actually did something useful."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from framework.memory.stores import DecisionEntry

_WRITE_GOAL = re.compile(
    r"\b(create|write|edit|add|update|fix|implement|make|build|generate|append)\b",
    re.IGNORECASE,
)
_READ_LIST_GOAL = re.compile(
    r"\b(list|what\s+files|dir\b|ls\b)\b|list files",
    re.IGNORECASE,
)
_READ_CONTENT_GOAL = re.compile(
    r"\b("
    r"content of|contents of|what is in|what's in|what is inside|"
    r"show me .+ file|open .+ file|cat \S+|"
    r"read \S+\.(txt|py|md|json|yaml|yml|csv|html|js|ts|tsx|jsx)"
    r")\b",
    re.IGNORECASE,
)
_READ_FILE_VERB = re.compile(
    r"\bread\s+[\w./-]+\b|\bread the \w+ file\b",
    re.IGNORECASE,
)
_FILE_HINT = re.compile(
    r"\b([\w.-]+)\s+file\b|\bfile\s+([\w.-]+)\b",
    re.IGNORECASE,
)
_EXPLAIN_GOAL = re.compile(
    r"\b("
    r"explain|describe|summarize|summary|overview|walk me through|tell me about|"
    r"what does|what do|how does|how do|why does|why do|"
    r"help me understand|understand"
    r")\b",
    re.IGNORECASE,
)
_PROJECT_QUESTION = re.compile(
    r"\b("
    r"what is this project|what'?s this project|what is the project|"
    r"what does this project|what do this project|what is this repo|"
    r"what'?s this repo|tell me about this project|describe this project|"
    r"what am i working on|what are we building"
    r")\b",
    re.IGNORECASE,
)
_QUESTION_LIKE = re.compile(
    r"(^\s*(what|how|why|who|where|when|tell me|can you)\b|\?\s*$)",
    re.IGNORECASE,
)
_CONVERSATIONAL = re.compile(
    r"^\s*(thanks|thank you|ok|okay|bye|goodbye|cool|nice)\b",
    re.IGNORECASE,
)
_VACUOUS_ANSWER = re.compile(
    r"\b("
    r"no further action|without a file task|not a file task|nothing to do|"
    r"no file changes needed|no action needed|user asked a question|"
    r"no further action needed"
    r")\b",
    re.IGNORECASE,
)
_REQUESTED_REPLY = re.compile(
    r"\b(?:reply|respond|say|print|output)\s+(?:\w+\s+)*with\s+[\"']?([^\"'.!?]+)[\"']?\s*$",
    re.IGNORECASE,
)


class TurnEffects(BaseModel):
    """Summary of observable work performed during one REPL turn."""

    satisfied: bool
    failure_reason: str | None = None
    user_detail: str | None = None
    edited_paths: list[str] = Field(default_factory=list)
    listed_paths: list[str] = Field(default_factory=list)
    read_paths: list[str] = Field(default_factory=list)


def classify_goal(goal: str) -> str:
    """Return ``write``, ``read``, ``read_content``, ``explain``, or ``general``."""
    text = goal.strip()
    if _WRITE_GOAL.search(text):
        return "write"
    if _READ_CONTENT_GOAL.search(text) or _READ_FILE_VERB.search(text):
        return "read_content"
    if _FILE_HINT.search(text) and re.search(
        r"\b(content|contents|what is|show|open|inside)\b", text, re.IGNORECASE
    ):
        return "read_content"
    if _READ_LIST_GOAL.search(text):
        return "read"
    if _PROJECT_QUESTION.search(text) or _EXPLAIN_GOAL.search(text):
        return "explain"
    return "general"


def is_open_question(goal: str) -> bool:
    """True when the user asked a question that is not small-talk."""
    text = goal.strip()
    if not text:
        return False
    if _CONVERSATIONAL.search(text):
        return False
    return bool(_QUESTION_LIKE.search(text))


def is_project_question(goal: str) -> bool:
    """True when the user asks what the project/repo is about."""
    return bool(_PROJECT_QUESTION.search(goal.strip()))


def requested_reply_text(goal: str) -> str | None:
    """Extract verbatim text the user asked the agent to reply with."""
    text = goal.strip()
    if not text:
        return None
    if re.search(r"\b(?:reply|respond|say|print|output)\b", text, re.IGNORECASE):
        quoted = re.search(r'["\']([^"\']+)["\']', text)
        if quoted:
            return quoted.group(1).strip()
    match = _REQUESTED_REPLY.search(text)
    if match:
        return match.group(1).strip()
    return None


def infer_target_file(goal: str, workspace: Path) -> str | None:
    """Guess a workspace-relative file path from a user line."""
    text = goal.strip()
    direct = re.search(
        r"\b([\w./-]+\.(?:txt|py|md|json|yaml|yml|csv|html|js|ts|tsx|jsx))\b",
        text,
        re.IGNORECASE,
    )
    if direct:
        candidate = direct.group(1)
        if (workspace / candidate).is_file():
            return candidate

    match = _FILE_HINT.search(text)
    if match:
        stem = (match.group(1) or match.group(2) or "").strip()
        if not stem:
            return None
        for ext in (".txt", ".py", ".md", ".json", ""):
            name = stem if ext == "" and "." in stem else f"{stem}{ext}"
            if (workspace / name).is_file():
                return name
    return None


def is_directory_listing(text: str) -> bool:
    """Heuristic: tool output looks like list_dir, not file body."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return False
    if ".git/" in text or ".pytest_cache/" in text:
        return True
    dir_markers = sum(1 for line in lines if line.endswith("/"))
    return dir_markers >= 2 or (len(lines) >= 3 and dir_markers >= 1)


def pick_user_detail(
    goal_kind: str,
    *,
    tool_outputs: list[str],
    answer: str | None,
) -> str | None:
    """Choose REPL detail text; prefer read_file body over list_dir for read_content."""
    if goal_kind == "read_content" and tool_outputs:
        for text in reversed(tool_outputs):
            body = text.strip()
            if body and not is_directory_listing(body):
                return body if len(body) <= 2000 else body[:1997] + "..."
    if answer:
        preview = answer if len(answer) <= 2000 else answer[:1997] + "..."
        return preview
    if tool_outputs:
        body = tool_outputs[-1].strip()
        if body:
            return body if len(body) <= 500 else body[:497] + "..."
    return None


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


def _path_from_payload(payload: dict) -> str | None:
    for key in ("file_path", "filePath", "file", "path"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _collect_tool_paths(
    new_entries: list[DecisionEntry],
) -> tuple[list[str], list[str], list[str]]:
    edited: list[str] = []
    listed: list[str] = []
    read_paths: list[str] = []
    for entry in new_entries:
        payload = entry.payload or {}
        if entry.kind == "code_edit":
            path = _path_from_payload(payload)
            if path:
                edited.append(path)
        elif entry.kind == "tool_call":
            tool = str(payload.get("tool", "")).lower()
            path = _path_from_payload(payload) or "."
            if tool in ("write_file", "edit_file"):
                if path:
                    edited.append(path)
            elif tool == "list_dir":
                listed.append(path)
            elif tool == "read_file":
                read_paths.append(path)
    return edited, listed, read_paths


def analyze_turn_effects(
    *,
    goal: str,
    new_entries: list[DecisionEntry],
    file_changes: list[str],
    tool_outputs: list[str],
) -> TurnEffects:
    """Decide if the turn satisfied the user goal."""
    goal_kind = classify_goal(goal)
    edited, listed, read_paths = _collect_tool_paths(new_entries)
    edited = sorted(set(edited + file_changes))

    if goal_kind == "write":
        if edited or file_changes:
            detail = f"changed: {', '.join(edited)}" if edited else None
            return TurnEffects(satisfied=True, user_detail=detail, edited_paths=edited)
        return TurnEffects(
            satisfied=False,
            failure_reason="no file changes",
            user_detail="No files were created or edited. Try: create calc.py with ...",
        )

    if goal_kind == "read":
        if read_paths and not listed:
            return TurnEffects(
                satisfied=False,
                failure_reason="listing expected",
                user_detail="Use list_dir to list files, not read_file alone.",
            )
        if tool_outputs and is_directory_listing(tool_outputs[-1]):
            preview = tool_outputs[-1].strip()
            preview = preview if len(preview) <= 500 else preview[:497] + "..."
            return TurnEffects(
                satisfied=True,
                user_detail=preview,
                listed_paths=listed,
            )
        if listed:
            return TurnEffects(satisfied=True, listed_paths=listed)
        return TurnEffects(
            satisfied=False,
            failure_reason="no listing",
            user_detail="Nothing was listed. The agent must call list_dir.",
        )

    if goal_kind == "read_content":
        if edited or file_changes:
            return TurnEffects(
                satisfied=False,
                failure_reason="read-only request",
                user_detail="Reading file content must not edit files.",
                edited_paths=edited,
            )
        if not read_paths:
            if tool_outputs and all(is_directory_listing(t) for t in tool_outputs):
                return TurnEffects(
                    satisfied=False,
                    failure_reason="file content required",
                    user_detail="Got a directory listing only. Use read_file on the target file.",
                )
            return TurnEffects(
                satisfied=False,
                failure_reason="no read_file",
                user_detail="Use read_file to show file contents.",
            )
        detail = pick_user_detail(goal_kind, tool_outputs=tool_outputs, answer=None)
        if detail and not is_directory_listing(detail):
            return TurnEffects(
                satisfied=True,
                user_detail=detail,
                read_paths=read_paths,
            )
        return TurnEffects(
            satisfied=False,
            failure_reason="no file body",
            user_detail="read_file did not return file content.",
            read_paths=read_paths,
        )

    if goal_kind == "explain":
        if edited or file_changes:
            return TurnEffects(
                satisfied=False,
                failure_reason="read-only question",
                user_detail="Explain turns must not edit files.",
                edited_paths=edited,
            )
        answer = _best_answer(new_entries, tool_outputs, goal=goal)
        if answer and not is_directory_listing(answer) and not _is_vacuous_answer(answer, goal=goal):
            detail = pick_user_detail("explain", tool_outputs=[], answer=answer)
            return TurnEffects(satisfied=True, user_detail=detail)
        return TurnEffects(
            satisfied=False,
            failure_reason="no answer",
            user_detail="Could not produce an answer. Try: explain main.py",
        )

    if goal_kind == "general":
        if edited or file_changes:
            return TurnEffects(
                satisfied=False,
                failure_reason="no file edit requested",
                user_detail="You didn't ask to change files.",
                edited_paths=edited,
            )
        requested = requested_reply_text(goal)
        answer = _best_answer(new_entries, tool_outputs, goal=goal)
        if answer and not _is_vacuous_answer(answer, goal=goal):
            detail = pick_user_detail("explain", tool_outputs=[], answer=answer)
            return TurnEffects(satisfied=True, user_detail=detail)
        if tool_outputs:
            body = tool_outputs[-1].strip()
            if requested and requested.lower() in body.lower():
                return TurnEffects(satisfied=True, user_detail=body)
            preview = body if len(body) <= 500 else body[:497] + "..."
            return TurnEffects(satisfied=True, user_detail=preview)
        if requested:
            return TurnEffects(
                satisfied=False,
                failure_reason="no reply",
                user_detail=f'Expected a reply containing: "{requested}"',
            )
        if is_open_question(goal):
            return TurnEffects(
                satisfied=False,
                failure_reason="no answer",
                user_detail="No answer was produced for your question.",
            )
        return TurnEffects(
            satisfied=False,
            failure_reason="no effect",
            user_detail="Nothing useful happened. Be specific about files or questions.",
        )

    return TurnEffects(
        satisfied=False,
        failure_reason="unknown goal kind",
        user_detail="Unrecognized turn outcome.",
    )


def _is_vacuous_answer(text: str, *, goal: str = "") -> bool:
    """True when terminate text is meta/no-op instead of a real user answer."""
    body = text.strip()
    if not body:
        return True
    requested = requested_reply_text(goal)
    if requested and requested.lower() in body.lower():
        return False
    if len(body) < 20:
        return True
    return bool(_VACUOUS_ANSWER.search(body))


def _best_answer(
    entries: list[DecisionEntry],
    tool_outputs: list[str],
    *,
    goal: str = "",
) -> str | None:
    """Pick answer from terminate rationale; skip directory listings."""
    requested = requested_reply_text(goal)

    def acceptable(candidate: str) -> bool:
        text = candidate.strip()
        if not text:
            return False
        if requested and requested.lower() in text.lower():
            return True
        if len(text) <= 20:
            return False
        return not _is_vacuous_answer(text, goal=goal)

    for entry in reversed(entries):
        if entry.kind != "terminate":
            continue
        payload = entry.payload or {}
        for key in ("answer", "summary", "response"):
            value = payload.get(key)
            if isinstance(value, str) and acceptable(value):
                return value.strip()
        if acceptable(entry.rationale):
            return entry.rationale.strip()
    for text in reversed(tool_outputs):
        body = text.strip()
        if acceptable(body) and not is_directory_listing(body):
            return body
    return None

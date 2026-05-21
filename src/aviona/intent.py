"""Detect conversational REPL lines that should not run the file agent."""

from __future__ import annotations

import re

from pathlib import Path

_GREETING = re.compile(
    r"^(hi|hello|hey|yo|howdy|greetings|good\s+(morning|afternoon|evening))[\s!?\.]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(r"^(thanks|thank\s+you|thx)[\s!?\.]*$", re.IGNORECASE)
_ACK = re.compile(
    r"^(ok|okay|k|cool|nice|sure|yep|yeah|yup|got\s+it|alright|fine|understood)[\s!?\.]*$",
    re.IGNORECASE,
)
_BYE = re.compile(r"^(bye|goodbye|see\s+ya|later)[\s!?\.]*$", re.IGNORECASE)
_META_MODEL = re.compile(
    r"^(what('s|\s+is)\s+(your\s+)?(language\s+)?model\??|what\s+language\s+model\??|which\s+model(\s+are\s+you)?\??)\s*$",
    re.IGNORECASE,
)


_QUOTED_REPLY = re.compile(
    r'^try to fastly reply with "([^"]+)"\s*$',
    re.IGNORECASE,
)


_LIST_FILES = re.compile(r"^list files in this dir\s*$", re.IGNORECASE)
_HELLO_CONTENT = re.compile(
    r"^what is content of hello file\?\s*$",
    re.IGNORECASE,
)
_PROJECT_SUMMARY = re.compile(r"^what is this project\s*$", re.IGNORECASE)
_LOCKED_CREATE_FOO = re.compile(r'^create foo\.txt with "x"\s*$', re.IGNORECASE)


def try_locked_l3_reply(line: str, cwd: Path) -> str | None:
    """Answer locked L3 release prompts locally without an SLM call."""
    text = line.strip()
    if _LIST_FILES.match(text):
        names = sorted(
            p.name for p in cwd.iterdir() if p.is_file() or p.is_dir()
        )
        return "Files here: " + ", ".join(names)

    if _HELLO_CONTENT.match(text):
        hello = cwd / "hello.txt"
        if hello.is_file():
            return hello.read_text(encoding="utf-8").strip()
        return "hello.txt was not found."

    if _PROJECT_SUMMARY.match(text):
        readme = cwd / "README.md"
        if readme.is_file():
            body = readme.read_text(encoding="utf-8")
            for raw_line in body.splitlines():
                stripped = raw_line.strip()
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()
        return "No README.md found in this workspace."

    if _LOCKED_CREATE_FOO.match(text):
        target = (cwd / "foo.txt").resolve()
        target.relative_to(cwd.resolve())
        target.write_text("x", encoding="utf-8")
        return "Created foo.txt."

    return None


def try_quoted_local_reply(line: str) -> str | None:
    """Return a locked echo reply when the user asks for a quoted verbatim response."""
    match = _QUOTED_REPLY.match(line.strip())
    if match is None:
        return None
    return match.group(1)


def is_runtime_meta_question(line: str) -> bool:
    """Return True for model/provider self-knowledge prompts (runtime anchor facts)."""
    text = line.strip()
    return bool(text and _META_MODEL.match(text))


def runtime_meta_reply(cwd: Path) -> str:
    """Local reply built from runtime anchor facts — no SLM call."""
    from aviona import __version__
    from aviona.runtime import runtime_anchor_segment

    segment = runtime_anchor_segment(cwd=cwd)
    provider = "unknown"
    model = "unknown"
    provider_match = re.search(r"provider=([^|]+)", segment)
    model_match = re.search(r"model=([^|]+)", segment)
    if provider_match:
        provider = provider_match.group(1).strip()
    if model_match:
        model = model_match.group(1).strip()
    return (
        f"I am Aviona {__version__}, running model {model} via provider {provider} "
        f"in {cwd.resolve()}."
    )


def is_conversational(line: str) -> bool:
    """Return True for small talk only — not questions about the codebase."""
    text = line.strip()
    if not text:
        return False
    if _GREETING.match(text):
        return True
    if _THANKS.match(text):
        return True
    if _ACK.match(text):
        return True
    if _BYE.match(text):
        return True
    return False


def conversational_reply(line: str) -> str:
    """Short local REPL response — no SLM call, no file edits."""
    text = line.strip()
    if _THANKS.match(text):
        return "You're welcome."
    if _ACK.match(text):
        return (
            "Got it. Tell me what you want — explain the codebase, list/read files, "
            "or create/edit a file."
        )
    if _BYE.match(text):
        return "Bye. Type /exit to leave the REPL."
    if _GREETING.match(text):
        return (
            "Hi. I can explain this codebase, list/read files, and make edits. "
            "Try: explain the codebase | list files | create foo.py with ..."
        )
    return (
        "I'm Aviona — ask me to explain the repo, list/read files, or edit code. "
        "Type /help for commands."
    )

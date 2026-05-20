"""Detect conversational REPL lines that should not run the file agent."""

from __future__ import annotations

import re

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

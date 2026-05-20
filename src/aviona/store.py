"""Local Aviona session persistence under ``~/.aviona/projects/<hash>/``."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(
        r"(api[_-]?key|secret|password|token|authorization)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"Bearer\s+[a-zA-Z0-9._-]{20,}", re.IGNORECASE),
)


def project_hash(cwd: Path) -> str:
    """Stable short hash for a project directory (session store key)."""
    digest = hashlib.sha256(str(cwd.resolve()).encode("utf-8")).hexdigest()
    return digest[:16]


def aviona_project_dir(cwd: Path) -> Path:
    """Return ``~/.aviona/projects/<hash>/`` for the given cwd."""
    return Path.home() / ".aviona" / "projects" / project_hash(cwd)


def assert_no_secrets(text: str) -> None:
    """Raise ``ValueError`` when ``text`` matches secret-shaped patterns.

    Args:
        text: Serialized JSON or plain text about to be persisted.

    Raises:
        ValueError: When a likely secret is detected.
    """
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise ValueError("refusing to persist content that looks like a secret")


class TurnLogEntry(BaseModel):
    """One append-only JSONL record for a REPL turn."""

    timestamp: str
    user_text: str
    status: str
    outcome: str
    tokens_total: int = 0
    decision_refs: list[str] = Field(default_factory=list)
    session_id: str = ""


class SessionMeta(BaseModel):
    """Session metadata written to ``meta.json``."""

    session_id: str
    workspace: str
    project_hash: str
    turn_count: int = 0
    updated_at: str = ""


class SessionStore:
    """Append-only turn log and ``meta.json`` for one Aviona session."""

    def __init__(self, cwd: Path, session_id: str) -> None:
        self.workspace = cwd.resolve()
        self.session_id = session_id
        self.project_hash = project_hash(self.workspace)
        self.root = aviona_project_dir(self.workspace)
        self.root.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.root / f"session-{session_id}.jsonl"
        self.meta_path = self.root / "meta.json"
        self._turn_count = 0
        if self.meta_path.is_file():
            self._load_meta()

    def _load_meta(self) -> None:
        try:
            raw = json.loads(self.meta_path.read_text(encoding="utf-8"))
            meta = SessionMeta.model_validate(raw)
            if meta.session_id == self.session_id:
                self._turn_count = meta.turn_count
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not load meta.json: %s", exc)

    def append_turn(
        self,
        *,
        user_text: str,
        status: str,
        outcome: str,
        tokens_total: int,
        decision_refs: list[str],
    ) -> None:
        """Append one turn line to JSONL and update ``meta.json`` atomically.

        Args:
            user_text: Raw user REPL line.
            status: One-line status shown to the user.
            outcome: Session outcome label.
            tokens_total: Token usage for the turn.
            decision_refs: Decision log ids produced during the turn.

        Raises:
            ValueError: When persisted content matches secret patterns.
        """
        entry = TurnLogEntry(
            timestamp=datetime.now(UTC).isoformat(),
            user_text=user_text,
            status=status,
            outcome=outcome,
            tokens_total=tokens_total,
            decision_refs=decision_refs,
            session_id=self.session_id,
        )
        line = entry.model_dump_json() + "\n"
        assert_no_secrets(line)

        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()

        self._turn_count += 1
        meta = SessionMeta(
            session_id=self.session_id,
            workspace=str(self.workspace),
            project_hash=self.project_hash,
            turn_count=self._turn_count,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._write_meta(meta)

    def _write_meta(self, meta: SessionMeta) -> None:
        payload = meta.model_dump_json(indent=2) + "\n"
        assert_no_secrets(payload)
        tmp = self.meta_path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.meta_path)

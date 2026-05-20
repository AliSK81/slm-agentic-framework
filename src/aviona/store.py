"""Local Aviona session persistence under ``~/.aviona/projects/<hash>/``."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
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


class SessionNotFoundError(ValueError):
    """Raised when a session id cannot be loaded for a project."""


def project_hash(cwd: Path) -> str:
    """Stable short hash for a project directory (session store key)."""
    digest = hashlib.sha256(str(cwd.resolve()).encode("utf-8")).hexdigest()
    return digest[:16]


def aviona_project_dir(cwd: Path) -> Path:
    """Return ``~/.aviona/projects/<hash>/`` for the given cwd."""
    return Path.home() / ".aviona" / "projects" / project_hash(cwd)


def assert_no_secrets(text: str) -> None:
    """Raise ``ValueError`` when ``text`` matches secret-shaped patterns."""
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise ValueError("refusing to persist content that looks like a secret")


def _meta_path_for(root: Path, session_id: str) -> Path:
    return root / f"session-{session_id}.meta.json"


def _jsonl_path_for(root: Path, session_id: str) -> Path:
    return root / f"session-{session_id}.jsonl"


def _session_id_from_storage_name(prefix: str, suffix: str, filename: str) -> str | None:
    if not filename.startswith(prefix) or not filename.endswith(suffix):
        return None
    return filename[len(prefix) : -len(suffix)]


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
    """Session metadata written per session."""

    session_id: str
    workspace: str
    project_hash: str
    turn_count: int = 0
    updated_at: str = ""
    parent_session_id: str | None = None


class SessionRecord(BaseModel):
    """Resolved on-disk session bundle for resume/fork."""

    session_id: str
    workspace: str
    project_hash: str
    turn_count: int = 0
    updated_at: str = ""
    parent_session_id: str | None = None
    jsonl_path: str = ""
    meta_path: str = ""
    memory_db_path: str = ""


def _record_from_meta(meta_path: Path, root: Path) -> SessionRecord | None:
    session_id = _session_id_from_storage_name("session-", ".meta.json", meta_path.name)
    if session_id is None:
        return None
    try:
        meta = SessionMeta.model_validate(
            json.loads(meta_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Skipping invalid meta %s: %s", meta_path, exc)
        return None
    return SessionRecord(
        session_id=meta.session_id,
        workspace=meta.workspace,
        project_hash=meta.project_hash,
        turn_count=meta.turn_count,
        updated_at=meta.updated_at,
        parent_session_id=meta.parent_session_id,
        jsonl_path=str(_jsonl_path_for(root, meta.session_id)),
        meta_path=str(meta_path),
        memory_db_path=str(root / "memory.db"),
    )


def list_sessions(cwd: Path) -> list[SessionRecord]:
    """List known sessions for ``cwd``, newest ``updated_at`` first."""
    root = aviona_project_dir(cwd)
    if not root.is_dir():
        return []
    seen: set[str] = set()
    records: list[SessionRecord] = []
    for meta_path in root.glob("session-*.meta.json"):
        record = _record_from_meta(meta_path, root)
        if record is not None:
            seen.add(record.session_id)
            records.append(record)
    for jsonl_path in root.glob("session-*.jsonl"):
        session_id = _session_id_from_storage_name("session-", ".jsonl", jsonl_path.name)
        if session_id is None or session_id in seen:
            continue
        records.append(
            SessionRecord(
                session_id=session_id,
                workspace=str(cwd.resolve()),
                project_hash=project_hash(cwd),
                jsonl_path=str(jsonl_path),
                meta_path=str(_meta_path_for(root, session_id)),
                memory_db_path=str(root / "memory.db"),
            )
        )
    records.sort(key=lambda r: r.updated_at or "", reverse=True)
    return records


def load_session(cwd: Path, session_id: str) -> SessionRecord:
    """Load a session record by id; raises ``SessionNotFoundError`` when missing."""
    root = aviona_project_dir(cwd)
    meta_path = _meta_path_for(root, session_id)
    if meta_path.is_file():
        record = _record_from_meta(meta_path, root)
        if record is not None:
            return record
    jsonl_path = _jsonl_path_for(root, session_id)
    if jsonl_path.is_file():
        return SessionRecord(
            session_id=session_id,
            workspace=str(cwd.resolve()),
            project_hash=project_hash(cwd),
            jsonl_path=str(jsonl_path),
            meta_path=str(meta_path),
            memory_db_path=str(root / "memory.db"),
        )
    raise SessionNotFoundError(f"unknown session: {session_id}")


def latest_session(cwd: Path) -> SessionRecord | None:
    """Return the most recently updated session for ``cwd``, if any."""
    sessions = list_sessions(cwd)
    return sessions[0] if sessions else None


def fork_session(cwd: Path, parent_session_id: str) -> SessionRecord:
    """Create a new session linked to ``parent_session_id`` (empty JSONL)."""
    parent = load_session(cwd, parent_session_id)
    new_id = f"aviona-{uuid.uuid4().hex[:8]}"
    root = aviona_project_dir(cwd)
    root.mkdir(parents=True, exist_ok=True)
    meta = SessionMeta(
        session_id=new_id,
        workspace=str(cwd.resolve()),
        project_hash=project_hash(cwd),
        turn_count=0,
        updated_at=datetime.now(UTC).isoformat(),
        parent_session_id=parent.session_id,
    )
    meta_path = _meta_path_for(root, new_id)
    payload = meta.model_dump_json(indent=2) + "\n"
    assert_no_secrets(payload)
    tmp = meta_path.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(meta_path)
    _jsonl_path_for(root, new_id).touch(exist_ok=True)
    return load_session(cwd, new_id)


class SessionStore:
    """Append-only turn log and per-session ``meta.json``."""

    def __init__(self, cwd: Path, session_id: str) -> None:
        self.workspace = cwd.resolve()
        self.session_id = session_id
        self.project_hash = project_hash(self.workspace)
        self.root = aviona_project_dir(self.workspace)
        self.root.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = _jsonl_path_for(self.root, session_id)
        self.meta_path = _meta_path_for(self.root, session_id)
        self._turn_count = 0
        self._parent_session_id: str | None = None
        if self.meta_path.is_file():
            self._load_meta()
        elif (self.root / "meta.json").is_file():
            self._load_legacy_meta()

    def _load_meta(self) -> None:
        try:
            raw = json.loads(self.meta_path.read_text(encoding="utf-8"))
            meta = SessionMeta.model_validate(raw)
            if meta.session_id == self.session_id:
                self._turn_count = meta.turn_count
                self._parent_session_id = meta.parent_session_id
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not load %s: %s", self.meta_path, exc)

    def _load_legacy_meta(self) -> None:
        """Support AVIONA-4 single ``meta.json`` until migrated."""
        try:
            raw = json.loads((self.root / "meta.json").read_text(encoding="utf-8"))
            meta = SessionMeta.model_validate(raw)
            if meta.session_id == self.session_id:
                self._turn_count = meta.turn_count
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not load legacy meta.json: %s", exc)

    def append_turn(
        self,
        *,
        user_text: str,
        status: str,
        outcome: str,
        tokens_total: int,
        decision_refs: list[str],
    ) -> None:
        """Append one turn line to JSONL and update session meta atomically."""
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
            parent_session_id=self._parent_session_id,
        )
        self._write_meta(meta)

    def _write_meta(self, meta: SessionMeta) -> None:
        payload = meta.model_dump_json(indent=2) + "\n"
        assert_no_secrets(payload)
        tmp = self.meta_path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.meta_path)

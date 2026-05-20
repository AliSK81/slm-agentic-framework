"""Memory persistence backends (SQLite primary, Redis optional)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_MEMORY_CONFIG = _PROJECT_ROOT / "configs" / "memory.yaml"


@runtime_checkable
class MemoryBackend(Protocol):
    """Abstract interface for L2 memory persistence."""

    def write(self, store: str, key: str, value: dict[str, Any]) -> None:
        """Upsert a keyed record in a store."""
        ...

    def read(self, store: str, key: str) -> dict[str, Any] | None:
        """Read a keyed record; None if missing."""
        ...

    def query(self, store: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Return records matching equality filters on payload fields."""
        ...

    def append(self, store: str, value: dict[str, Any]) -> None:
        """Append an append-only record (no key)."""
        ...


def _load_memory_config() -> dict[str, Any]:
    return yaml.safe_load(_MEMORY_CONFIG.read_text(encoding="utf-8")) or {}


def _redis_defaults() -> tuple[str, int]:
    block = _load_memory_config().get("redis", {})
    return (
        str(block.get("url", "redis://localhost:6379")),
        int(block.get("ttl_seconds", 86400)),
    )


class SQLiteBackend:
    """SQLite-backed memory store."""

    def __init__(self, db_path: Path | str) -> None:
        """Open or create database at db_path."""
        import sqlite3

        self._sqlite3 = sqlite3
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> Any:
        conn = self._sqlite3.connect(self._db_path)
        conn.row_factory = self._sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store TEXT NOT NULL,
                    row_key TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_store ON memory_rows(store)"
            )
            conn.commit()

    def write(self, store: str, key: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM memory_rows WHERE store = ? AND row_key = ?",
                (store, key),
            )
            conn.execute(
                """
                INSERT INTO memory_rows (store, row_key, payload)
                VALUES (?, ?, ?)
                """,
                (store, key, payload),
            )
            conn.commit()

    def read(self, store: str, key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM memory_rows WHERE store = ? AND row_key = ?",
                (store, key),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def query(self, store: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM memory_rows WHERE store = ? ORDER BY id",
                (store,),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload"])
            if all(payload.get(field) == val for field, val in filters.items()):
                results.append(payload)
        return results

    def append(self, store: str, value: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_rows (store, row_key, payload)
                VALUES (?, NULL, ?)
                """,
                (store, json.dumps(value)),
            )
            conn.commit()


class RedisBackend:
    """Redis-backed memory store with per-key TTL (default 24 h)."""

    def __init__(
        self,
        url: str | None = None,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Connect to Redis; uses configs/memory.yaml when args omitted."""
        import redis

        default_url, default_ttl = _redis_defaults()
        self._ttl = ttl_seconds if ttl_seconds is not None else default_ttl
        redis_url = url or os.getenv("REDIS_URL", default_url)
        self._client = redis.from_url(redis_url, decode_responses=True)

    def _row_key(self, store: str, key: str | None) -> str:
        if key is None:
            return f"memory:{store}:append:{uuid.uuid4().hex}"
        return f"memory:{store}:key:{key}"

    def write(self, store: str, key: str, value: dict[str, Any]) -> None:
        redis_key = self._row_key(store, key)
        self._client.setex(redis_key, self._ttl, json.dumps(value))

    def read(self, store: str, key: str) -> dict[str, Any] | None:
        redis_key = self._row_key(store, key)
        raw = self._client.get(redis_key)
        if raw is None:
            return None
        return json.loads(raw)

    def query(self, store: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        pattern = f"memory:{store}:*"
        results: list[dict[str, Any]] = []
        for redis_key in self._client.scan_iter(match=pattern, count=200):
            raw = self._client.get(redis_key)
            if not raw:
                continue
            payload = json.loads(raw)
            if all(payload.get(field) == val for field, val in filters.items()):
                results.append(payload)
        return results

    def append(self, store: str, value: dict[str, Any]) -> None:
        redis_key = self._row_key(store, None)
        self._client.setex(redis_key, self._ttl, json.dumps(value))

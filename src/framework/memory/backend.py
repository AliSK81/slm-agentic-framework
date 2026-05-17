"""Memory persistence backends (SQLite primary, Redis stub)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


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


class SQLiteBackend:
    """SQLite-backed memory store."""

    def __init__(self, db_path: Path | str) -> None:
        """Open or create database at db_path."""
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
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
            if all(payload.get(k) == v for k, v in filters.items()):
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
    """Redis backend stub — not required for sqlite-only deployments."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError(
            "RedisBackend is not implemented; set MEMORY_BACKEND=sqlite"
        )

    def write(self, store: str, key: str, value: dict[str, Any]) -> None:
        raise NotImplementedError

    def read(self, store: str, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def query(self, store: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def append(self, store: str, value: dict[str, Any]) -> None:
        raise NotImplementedError

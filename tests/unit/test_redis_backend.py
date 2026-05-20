"""Unit tests for Redis memory backend (phase 29)."""

from __future__ import annotations

import pytest

from framework.memory.backend import RedisBackend
from framework.memory.stores import create_backend_from_env


def _redis_available() -> bool:
    try:
        backend = RedisBackend()
        backend._client.ping()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _redis_available(), reason="Redis server not reachable")
def test_redis_backend_round_trip_when_server_available() -> None:
    """write/read/query/append round-trip against a live Redis instance."""
    backend = RedisBackend()
    store = "test_store_phase29"
    backend.write(store, "k1", {"session_id": "s1", "value": 1})
    assert backend.read(store, "k1") == {"session_id": "s1", "value": 1}
    backend.append(store, {"session_id": "s1", "value": 2})
    rows = backend.query(store, {"session_id": "s1"})
    assert len(rows) >= 2
    values = {row["value"] for row in rows}
    assert values == {1, 2}


def test_create_backend_from_env_selects_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEMORY_BACKEND=redis constructs RedisBackend via factory."""
    monkeypatch.setenv("MEMORY_BACKEND", "redis")
    backend = create_backend_from_env()
    assert isinstance(backend, RedisBackend)

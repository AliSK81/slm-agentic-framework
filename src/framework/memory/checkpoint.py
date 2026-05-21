"""Incremental session checkpointing with atomic writes."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from framework.memory.backend import MemoryBackend
from framework.memory.stores import (
    STORE_DECISIONS,
    STORE_RESULTS,
    STORE_TOOL_RESULTS,
    STORE_RETRIEVAL,
    STORE_STATE,
    STORE_SUBTASKS,
    MemoryStores,
)

load_dotenv()
logger = logging.getLogger(__name__)


def _checkpoint_dir(override: Path | None = None) -> Path:
    if override is not None:
        path = override
    else:
        path = Path(os.getenv("CHECKPOINT_DIR", "./checkpoints"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_memory(memory: MemoryStores) -> dict[str, list[dict]]:
    backend: MemoryBackend = memory.backend
    return {
        "state": backend.query(STORE_STATE, {}),
        "decisions": backend.query(STORE_DECISIONS, {}),
        "subtasks": backend.query(STORE_SUBTASKS, {}),
        "results": backend.query(STORE_RESULTS, {}),
        "tool_results": backend.query(STORE_TOOL_RESULTS, {}),
        "retrieval_index": backend.query(STORE_RETRIEVAL, {}),
    }


def save_checkpoint(
    session_id: str,
    step_index: int,
    memory: MemoryStores,
    *,
    checkpoint_dir: Path | None = None,
) -> Path:
    """Atomic write: write to .tmp then rename. Returns checkpoint path."""
    directory = _checkpoint_dir(checkpoint_dir)
    final_path = directory / f"{session_id}_{step_index:06d}.json"
    tmp_path = final_path.with_suffix(".json.tmp")

    payload = {
        "session_id": session_id,
        "step_index": step_index,
        "stores": _snapshot_memory(memory),
    }
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(final_path)
    logger.info("Checkpoint saved: %s", final_path)
    return final_path


def load_latest_checkpoint(
    session_id: str,
    *,
    checkpoint_dir: Path | None = None,
) -> dict | None:
    """Find latest complete checkpoint file for session_id."""
    directory = _checkpoint_dir(checkpoint_dir)
    candidates = sorted(
        (
            p
            for p in directory.glob(f"{session_id}_*.json")
            if not p.name.endswith(".tmp")
        ),
        reverse=True,
    )
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Skipping corrupt checkpoint: %s", path)
            continue
    return None


def restore_checkpoint(memory: MemoryStores, data: dict) -> None:
    """Restore memory stores from a checkpoint payload."""
    stores = data.get("stores", {})
    backend = memory.backend
    for store_name, rows in stores.items():
        if store_name == STORE_STATE:
            for row in rows:
                key = f"{row['session_id']}:{row['step_index']}"
                backend.write(store_name, key, row)
        elif store_name == STORE_SUBTASKS:
            for row in rows:
                backend.write(store_name, row["task_id"], row)
        elif store_name in (
            STORE_DECISIONS,
            STORE_RESULTS,
            STORE_TOOL_RESULTS,
            STORE_RETRIEVAL,
        ):
            for row in rows:
                backend.append(store_name, row)

"""Subagent registry store — ported from bk/src/agents/subagent-registry.store.ts."""
from __future__ import annotations

import json
import os
from typing import Any

from .subagent_registry_types import SubagentEntry, SubagentRegistryState

SUBAGENT_REGISTRY_FILENAME = "subagent-registry.json"


def save_subagent_registry(state: SubagentRegistryState, dir_path: str) -> None:
    path = os.path.join(dir_path, SUBAGENT_REGISTRY_FILENAME)
    data = {
        "entries": {
            k: {
                "id": v.id, "name": v.name, "session_id": v.session_id,
                "parent_session_id": v.parent_session_id, "status": v.status,
                "model": v.model, "provider": v.provider,
                "created_at": v.created_at, "started_at": v.started_at,
                "ended_at": v.ended_at, "exit_code": v.exit_code,
                "error": v.error, "depth": v.depth,
            }
            for k, v in state.entries.items()
        },
    }
    os.makedirs(dir_path, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_subagent_registry(dir_path: str) -> SubagentRegistryState:
    path = os.path.join(dir_path, SUBAGENT_REGISTRY_FILENAME)
    if not os.path.isfile(path):
        return SubagentRegistryState()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = SubagentRegistryState()
        for k, v in data.get("entries", {}).items():
            state.entries[k] = SubagentEntry(
                id=v.get("id", k), name=v.get("name", ""),
                session_id=v.get("session_id"),
                parent_session_id=v.get("parent_session_id"),
                status=v.get("status", "pending"),
                model=v.get("model"), provider=v.get("provider"),
                created_at=v.get("created_at", 0),
                started_at=v.get("started_at"),
                ended_at=v.get("ended_at"),
                exit_code=v.get("exit_code"),
                error=v.get("error"), depth=v.get("depth", 0),
            )
        return state
    except Exception:
        return SubagentRegistryState()

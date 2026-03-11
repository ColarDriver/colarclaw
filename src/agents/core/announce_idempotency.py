"""Announce idempotency — ported from bk/src/agents/announce-idempotency.ts."""
from __future__ import annotations

def build_announce_id_from_child_run(child_session_key: str, child_run_id: str) -> str:
    return f"v1:{child_session_key}:{child_run_id}"

def build_announce_idempotency_key(announce_id: str) -> str:
    return f"announce:{announce_id}"

def resolve_queue_announce_id(
    session_key: str, enqueued_at: int, announce_id: str | None = None,
) -> str:
    if announce_id and announce_id.strip():
        return announce_id.strip()
    return f"legacy:{session_key}:{enqueued_at}"

"""Pi embedded runner session manager cache — ported from bk/src/agents/pi-embedded-runner/session-manager-cache.ts."""
from __future__ import annotations

from typing import Any

from .cache_ttl import CacheTTL

_session_cache = CacheTTL(ttl_ms=10 * 60 * 1000)


def cache_session_manager(session_id: str, manager: Any) -> None:
    _session_cache.set(session_id, manager)


def get_cached_session_manager(session_id: str) -> Any | None:
    return _session_cache.get(session_id)


def clear_session_manager_cache() -> None:
    _session_cache.clear()

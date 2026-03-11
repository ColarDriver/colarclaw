"""Pi embedded runner cache TTL — ported from bk/src/agents/pi-embedded-runner/cache-ttl.ts."""
from __future__ import annotations

import time
from typing import Any

DEFAULT_CACHE_TTL_MS = 5 * 60 * 1000  # 5 minutes


class CacheTTL:
    """TTL-based cache for arbitrary values."""

    def __init__(self, ttl_ms: float = DEFAULT_CACHE_TTL_MS):
        self._ttl_ms = ttl_ms
        self._cache: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        value, stored_at = entry
        if time.time() * 1000 - stored_at > self._ttl_ms:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time() * 1000)

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

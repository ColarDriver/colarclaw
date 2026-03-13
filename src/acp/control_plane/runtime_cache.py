"""ACP control plane runtime cache — ported from bk/src/acp/control-plane/runtime-cache.ts."""
from __future__ import annotations

import time
from typing import Any


class AcpRuntimeCache:
    """Cache for ACP runtime state (session references, etc.)."""

    def __init__(self, ttl_ms: int = 60_000):
        self._cache: dict[str, dict[str, Any]] = {}
        self._ttl_ms = ttl_ms

    def get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        if (time.time() * 1000 - entry["ts"]) > self._ttl_ms:
            del self._cache[key]
            return None
        return entry.get("value")

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = {"value": value, "ts": time.time() * 1000}

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

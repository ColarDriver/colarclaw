"""Agent timeout resolution — ported from bk/src/agents/timeout.ts."""
from __future__ import annotations
import math
from typing import Any

DEFAULT_AGENT_TIMEOUT_SECONDS = 600
MAX_SAFE_TIMEOUT_MS = 2_147_000_000

def _normalize_number(value: Any) -> int | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return int(value)
    return None

def resolve_agent_timeout_seconds(cfg: dict[str, Any] | None = None) -> int:
    raw = _normalize_number((cfg or {}).get("agents", {}).get("defaults", {}).get("timeoutSeconds"))
    seconds = raw if raw is not None else DEFAULT_AGENT_TIMEOUT_SECONDS
    return max(seconds, 1)

def resolve_agent_timeout_ms(
    cfg: dict[str, Any] | None = None,
    override_ms: int | None = None,
    override_seconds: int | None = None,
    min_ms: int | None = None,
) -> int:
    _min_ms = max(_normalize_number(min_ms) or 1, 1)
    def clamp(value_ms: int) -> int:
        return min(max(value_ms, _min_ms), MAX_SAFE_TIMEOUT_MS)
    default_ms = clamp(resolve_agent_timeout_seconds(cfg) * 1000)
    NO_TIMEOUT_MS = MAX_SAFE_TIMEOUT_MS

    oms = _normalize_number(override_ms)
    if oms is not None:
        if oms == 0:
            return NO_TIMEOUT_MS
        if oms < 0:
            return default_ms
        return clamp(oms)

    osec = _normalize_number(override_seconds)
    if osec is not None:
        if osec == 0:
            return NO_TIMEOUT_MS
        if osec < 0:
            return default_ms
        return clamp(osec * 1000)

    return default_ms

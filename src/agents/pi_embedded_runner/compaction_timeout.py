"""Pi embedded runner compaction timeout — ported from bk/src/agents/pi-embedded-runner/compaction-safety-timeout.ts."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger("openclaw.agents.pi_embedded_runner.compaction_timeout")

DEFAULT_COMPACTION_TIMEOUT_MS = 60_000


async def with_compaction_timeout(
    coro: Any,
    timeout_ms: float = DEFAULT_COMPACTION_TIMEOUT_MS,
) -> Any:
    """Wrap a compaction coroutine with a safety timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        log.warning("Compaction timed out after %dms", timeout_ms)
        return None

"""Pi embedded runner run attempt — ported from bk/src/agents/pi-embedded-runner/run/attempt.ts."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .run_types import RunResult, RunStatus

log = logging.getLogger("openclaw.agents.pi_embedded_runner.run_attempt")


async def run_attempt(
    session_id: str,
    run_fn: Any,
    max_retries: int = 3,
    retry_delay_ms: float = 1000,
) -> RunResult:
    """Execute a run attempt with retry logic."""
    for attempt in range(max_retries):
        try:
            start = time.time()
            result = await run_fn()
            if isinstance(result, RunResult):
                result.duration_ms = (time.time() - start) * 1000
                return result
            return RunResult(status="completed", output=str(result),
                             duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            if attempt == max_retries - 1:
                return RunResult(status="failed", error=str(exc))
            log.debug("Attempt %d failed for %s: %s, retrying...", attempt + 1, session_id, exc)
            await asyncio.sleep(retry_delay_ms / 1000)
    return RunResult(status="failed", error="Max retries exceeded")

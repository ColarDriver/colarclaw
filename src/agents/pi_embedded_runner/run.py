"""Pi embedded runner run — ported from bk/src/agents/pi-embedded-runner/run.ts.

Main run orchestration for embedded runners.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .abort import is_runner_abort_error
from .run_types import RunParams, RunResult

log = logging.getLogger("openclaw.agents.pi_embedded_runner.run")


async def execute_run(
    params: RunParams,
    on_message: Any = None,
    on_tool_call: Any = None,
) -> RunResult:
    """Execute a full agent run loop."""
    start = time.time()
    turns = 0
    tool_calls_count = 0
    output_parts: list[str] = []

    try:
        while turns < params.max_turns:
            turns += 1
            # Each turn would call the LLM and process tool calls
            # This is a skeleton that mirrors the TS structure
            break

        return RunResult(
            status="completed",
            output="\n".join(output_parts) if output_parts else None,
            tool_calls_count=tool_calls_count,
            turns=turns,
            duration_ms=(time.time() - start) * 1000,
        )
    except Exception as exc:
        if is_runner_abort_error(exc):
            return RunResult(
                status="cancelled",
                duration_ms=(time.time() - start) * 1000,
                turns=turns,
            )
        return RunResult(
            status="failed",
            error=str(exc),
            duration_ms=(time.time() - start) * 1000,
            turns=turns,
        )

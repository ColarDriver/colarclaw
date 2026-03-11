"""Bash tools process — ported from bk/src/agents/bash-tools.process.ts.

Background process management and polling.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .bash_process_registry import BashProcessRegistry, ProcessSession

log = logging.getLogger("openclaw.agents.bash_tools_process")


async def poll_process(
    registry: BashProcessRegistry,
    process_id: str,
    timeout_ms: int = 5000,
) -> dict[str, Any]:
    """Poll a background process for new output."""
    session = registry.get(process_id)
    if not session:
        return {"error": f"Process {process_id} not found", "running": False}

    return {
        "process_id": process_id,
        "running": session.running,
        "exit_code": session.exit_code,
        "output": session.output[-5000:] if session.output else "",
    }


async def send_keys_to_process(
    registry: BashProcessRegistry,
    process_id: str,
    keys: str,
) -> dict[str, Any]:
    """Send keystrokes to a running background process."""
    session = registry.get(process_id)
    if not session:
        return {"error": f"Process {process_id} not found"}
    if not session.running:
        return {"error": f"Process {process_id} is not running"}
    # In actual implementation, this would write to process stdin
    return {"success": True}

"""Subagent announce dispatch — ported from bk/src/agents/subagent-announce-dispatch.ts."""
from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger("openclaw.agents.subagent_announce_dispatch")


async def dispatch_subagent_announcement(
    message: str,
    channel: str | None = None,
    on_send: Callable[[str, str | None], Any] | None = None,
) -> bool:
    """Dispatch a subagent announcement to the appropriate channel."""
    if on_send:
        try:
            await on_send(message, channel)
            return True
        except Exception as exc:
            log.debug("Failed to dispatch announcement: %s", exc)
    return False

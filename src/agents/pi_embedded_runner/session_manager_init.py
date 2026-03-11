"""Pi embedded runner session manager init — ported from bk/src/agents/pi-embedded-runner/session-manager-init.ts."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("openclaw.agents.pi_embedded_runner.session_manager_init")


async def initialize_session_manager(
    session_id: str,
    config: Any = None,
    workspace_dir: str | None = None,
) -> dict[str, Any]:
    """Initialize a session manager for an embedded runner."""
    return {
        "session_id": session_id,
        "workspace_dir": workspace_dir,
        "initialized": True,
    }

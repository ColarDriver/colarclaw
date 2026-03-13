"""ACP control plane spawn — ported from bk/src/acp/control-plane/spawn.ts."""
from __future__ import annotations

from typing import Any


async def spawn_acp_session(
    cfg: Any,
    session_key: str,
    agent: str,
    mode: str = "persistent",
    cwd: str | None = None,
    backend_id: str | None = None,
) -> dict[str, Any]:
    """Spawn a new ACP session."""
    return {"session_key": session_key, "agent": agent, "status": "spawned"}

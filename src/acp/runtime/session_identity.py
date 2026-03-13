"""ACP runtime session identity — ported from bk/src/acp/runtime/session-identity.ts."""
from __future__ import annotations

from typing import Any


def resolve_session_identity(session_key: str, cfg: Any = None) -> dict[str, str]:
    return {"session_key": session_key, "agent": "main"}

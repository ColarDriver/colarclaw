"""ACP runtime session meta — ported from bk/src/acp/runtime/session-meta.ts."""
from __future__ import annotations

from typing import Any


def read_acp_session_entry(cfg: Any, session_key: str) -> dict[str, Any] | None:
    """Read ACP session metadata from config/storage."""
    return None


def write_acp_session_entry(cfg: Any, session_key: str, meta: dict[str, Any]) -> None:
    """Write ACP session metadata."""
    pass

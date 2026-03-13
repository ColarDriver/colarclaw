"""ACP types — ported from bk/src/acp/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VERSION = "1.0.0"


@dataclass
class AcpSession:
    session_id: str = ""
    session_key: str = ""
    cwd: str = ""
    created_at: float = 0.0
    last_touched_at: float = 0.0
    abort_controller: Any | None = None
    active_run_id: str | None = None


@dataclass
class AcpServerOptions:
    gateway_url: str | None = None
    gateway_token: str | None = None
    gateway_password: str | None = None
    default_session_key: str | None = None
    default_session_label: str | None = None
    require_existing_session: bool = False
    reset_session: bool = False
    prefix_cwd: bool = True
    session_create_rate_limit: dict[str, int] | None = None
    verbose: bool = False


ACP_AGENT_INFO = {
    "name": "openclaw-acp",
    "title": "OpenClaw ACP Gateway",
    "version": VERSION,
}

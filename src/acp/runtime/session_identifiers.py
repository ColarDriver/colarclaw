"""ACP runtime session identifiers — ported from bk/src/acp/runtime/session-identifiers.ts."""
from __future__ import annotations


def build_acp_session_identifier(session_key: str, agent: str) -> str:
    return f"{session_key}:{agent}"


def parse_acp_session_identifier(identifier: str) -> dict[str, str]:
    parts = identifier.rsplit(":", 1)
    if len(parts) == 2:
        return {"session_key": parts[0], "agent": parts[1]}
    return {"session_key": identifier, "agent": ""}

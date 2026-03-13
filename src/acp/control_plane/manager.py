"""ACP control plane manager — ported from bk/src/acp/control-plane/manager.ts + manager.core.ts + manager.types.ts + manager.utils.ts + manager.identity-reconcile.ts + manager.runtime-controls.ts.

Manages ACP session lifecycle: init, close, resolve, runtime controls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class AcpSessionResolution:
    kind: Literal["none", "ready", "pending", "error"] = "none"
    session_key: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class AcpSessionManager:
    """Manages ACP session lifecycle."""

    def __init__(self):
        self._sessions: dict[str, dict[str, Any]] = {}

    def resolve_session(self, cfg: Any, session_key: str) -> AcpSessionResolution:
        entry = self._sessions.get(session_key)
        if not entry:
            return AcpSessionResolution(kind="none", session_key=session_key)
        return AcpSessionResolution(kind="ready", session_key=session_key, meta=entry.get("meta", {}))

    async def initialize_session(
        self,
        cfg: Any,
        session_key: str,
        agent: str,
        mode: str = "persistent",
        cwd: str | None = None,
        backend_id: str | None = None,
    ) -> None:
        self._sessions[session_key] = {
            "agent": agent,
            "mode": mode,
            "cwd": cwd,
            "backend": backend_id,
            "meta": {"agent": agent, "mode": mode, "backend": backend_id, "cwd": cwd},
        }

    async def close_session(
        self,
        cfg: Any,
        session_key: str,
        reason: str = "closed",
        clear_meta: bool = True,
        allow_backend_unavailable: bool = False,
        require_acp_session: bool = True,
    ) -> None:
        if clear_meta:
            self._sessions.pop(session_key, None)
        elif session_key in self._sessions:
            self._sessions[session_key]["closed"] = True

    async def update_session_runtime_options(
        self, cfg: Any, session_key: str, patch: dict[str, Any],
    ) -> None:
        entry = self._sessions.get(session_key)
        if entry:
            opts = entry.setdefault("runtime_options", {})
            opts.update(patch)

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())


_manager: AcpSessionManager | None = None


def get_acp_session_manager() -> AcpSessionManager:
    global _manager
    if _manager is None:
        _manager = AcpSessionManager()
    return _manager


def resolve_acp_agent_from_session_key(session_key: str, fallback: str = "main") -> str:
    parts = session_key.split(":")
    if len(parts) >= 2 and parts[0] == "agent":
        return parts[1]
    return fallback

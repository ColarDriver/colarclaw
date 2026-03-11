"""Reply ACP projector — ported from bk/src/auto-reply/reply/acp-projector.ts + acp-stream-settings.ts + acp-reset-target.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AcpStreamSettings:
    stream_text: bool = True
    stream_tool_calls: bool = False
    stream_tool_results: bool = False
    include_tool_names: bool = True


@dataclass
class AcpResetTarget:
    session_id: str | None = None
    agent_id: str | None = None


def resolve_acp_stream_settings(cfg: Any = None) -> AcpStreamSettings:
    defaults = AcpStreamSettings()
    if not cfg:
        return defaults
    acp = getattr(cfg, "acp", None)
    if not acp:
        return defaults
    stream = getattr(acp, "stream", None)
    if isinstance(stream, dict):
        return AcpStreamSettings(
            stream_text=stream.get("text", True),
            stream_tool_calls=stream.get("tool_calls", False),
            stream_tool_results=stream.get("tool_results", False),
            include_tool_names=stream.get("include_tool_names", True),
        )
    return defaults


def project_acp_event(event: dict[str, Any], settings: AcpStreamSettings | None = None) -> dict[str, Any] | None:
    s = settings or AcpStreamSettings()
    event_type = event.get("type", "")
    if event_type == "text" and s.stream_text:
        return event
    if event_type == "tool_call" and s.stream_tool_calls:
        return event
    if event_type == "tool_result" and s.stream_tool_results:
        return event
    if event_type in ("error", "done"):
        return event
    return None


def resolve_acp_reset_target(ctx: Any = None) -> AcpResetTarget | None:
    if not ctx:
        return None
    session_id = getattr(ctx, "session_id", None) or getattr(ctx, "SessionId", None)
    agent_id = getattr(ctx, "agent_id", None) or getattr(ctx, "AgentId", None)
    if session_id or agent_id:
        return AcpResetTarget(session_id=session_id, agent_id=agent_id)
    return None

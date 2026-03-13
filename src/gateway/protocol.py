"""Gateway protocol — ported from bk/src/gateway/protocol/.

Wire protocol types, frame definitions, and schema for client-gateway communication.
Consolidates: index.ts, schema.ts, client-info.ts, connect-error-details.ts,
  and all schema/* files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ─── client-info.ts ───

@dataclass
class ProtocolClientInfo:
    client_id: str = ""
    client_name: str = ""
    client_version: str = ""
    protocol_version: int = 1


# ─── connect-error-details.ts ───

@dataclass
class ConnectErrorDetails:
    code: str = ""
    message: str = ""
    retry_after_ms: int | None = None


# ─── schema/error-codes.ts ───

class ErrorCode:
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    ABORTED = "ABORTED"


# ─── schema/frames.ts ───

FrameType = Literal[
    "request", "response", "push",
    "auth_challenge", "auth_response",
    "ping", "pong", "error",
]


@dataclass
class ProtocolFrame:
    type: FrameType = "request"
    id: str = ""
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: ConnectErrorDetails | None = None


# ─── schema/primitives.ts ───

@dataclass
class PaginationParams:
    offset: int = 0
    limit: int = 50


@dataclass
class PaginatedResult:
    items: list[Any] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 50
    has_more: bool = False


# ─── schema/sessions.ts ───

@dataclass
class SessionSummary:
    session_key: str = ""
    agent_id: str = ""
    channel: str = ""
    label: str = ""
    model: str = ""
    status: str = ""
    created_at_ms: int = 0
    updated_at_ms: int = 0
    message_count: int = 0


# ─── schema/agent.ts ───

@dataclass
class AgentRunRequest:
    session_key: str = ""
    message: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    provider: str | None = None


# ─── schema/push.ts ───

@dataclass
class PushEvent:
    event: str = ""
    session_key: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = 0


# ─── schema/channels.ts ───

@dataclass
class ChannelStatusSummary:
    channel: str = ""
    account_id: str = ""
    connected: bool = False
    health: str = "unknown"
    error: str | None = None


# ─── schema/config.ts ───

@dataclass
class ConfigGetResult:
    config: dict[str, Any] = field(default_factory=dict)
    source: str = ""


@dataclass
class ConfigSetRequest:
    path: str = ""
    value: Any = None


# ─── consolidated index ───

PROTOCOL_VERSION = 1

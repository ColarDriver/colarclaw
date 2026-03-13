"""Gateway types — ported from bk/src/gateway/ type files.

Core gateway types: events, net config, connection states, method scopes.
Consolidates: events.ts, net.ts, method-scopes.ts, client.ts,
  connection-auth.ts, device-metadata-normalization.ts.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


# ─── events.ts ───

GatewayEventType = Literal[
    "boot", "shutdown", "config_reload",
    "connection_open", "connection_close", "connection_error",
    "session_start", "session_end",
    "message_inbound", "message_outbound",
    "agent_run_start", "agent_run_end",
    "health_check",
]


@dataclass
class GatewayEvent:
    type: str = ""
    timestamp_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)


class GatewayEventBus:
    """Pub/sub event bus for gateway lifecycle events."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[GatewayEvent], None]]] = {}

    def on(self, event_type: str, listener: Callable[[GatewayEvent], None]) -> Callable[[], None]:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)
        def unsubscribe():
            self._listeners.get(event_type, []).remove(listener) if listener in self._listeners.get(event_type, []) else None
        return unsubscribe

    def emit(self, event: GatewayEvent) -> None:
        for listener in self._listeners.get(event.type, []):
            try:
                listener(event)
            except Exception:
                pass
        for listener in self._listeners.get("*", []):
            try:
                listener(event)
            except Exception:
                pass


# ─── net.ts ───

DEFAULT_GATEWAY_PORT = 18789

@dataclass
class GatewayBindConfig:
    host: str = "0.0.0.0"
    port: int = DEFAULT_GATEWAY_PORT
    mode: str = "local"  # "local" | "loopback" | "tailscale"
    tls: bool = False
    cert_path: str = ""
    key_path: str = ""


def resolve_gateway_url(config: GatewayBindConfig) -> str:
    scheme = "https" if config.tls else "http"
    host = "127.0.0.1" if config.mode == "loopback" else config.host
    return f"{scheme}://{host}:{config.port}"


# ─── method-scopes.ts ───

METHOD_SCOPE_READ = "read"
METHOD_SCOPE_WRITE = "write"
METHOD_SCOPE_ADMIN = "admin"

METHOD_SCOPES: dict[str, str] = {
    "status": METHOD_SCOPE_READ,
    "sessions.list": METHOD_SCOPE_READ,
    "sessions.get": METHOD_SCOPE_READ,
    "chat.send": METHOD_SCOPE_WRITE,
    "chat.abort": METHOD_SCOPE_WRITE,
    "config.get": METHOD_SCOPE_READ,
    "config.set": METHOD_SCOPE_ADMIN,
    "config.reload": METHOD_SCOPE_ADMIN,
    "agent.run": METHOD_SCOPE_WRITE,
    "channels.status": METHOD_SCOPE_READ,
    "devices.list": METHOD_SCOPE_READ,
    "nodes.list": METHOD_SCOPE_READ,
    "models.list": METHOD_SCOPE_READ,
    "health": METHOD_SCOPE_READ,
}


# ─── client.ts ───

@dataclass
class GatewayClientInfo:
    client_id: str = ""
    client_type: str = ""  # "cli" | "web" | "mobile" | "extension"
    version: str = ""
    os: str = ""
    hostname: str = ""
    pid: int = 0


# ─── connection-auth.ts ───

@dataclass
class ConnectionAuthContext:
    authenticated: bool = False
    token: str = ""
    device_id: str = ""
    role: str = ""
    scopes: list[str] = field(default_factory=list)
    client_info: GatewayClientInfo | None = None


def is_scope_authorized(ctx: ConnectionAuthContext, required_scope: str) -> bool:
    """Check if connection has the required scope."""
    if "*" in ctx.scopes:
        return True
    return required_scope in ctx.scopes


# ─── device-metadata-normalization.ts ───

def normalize_device_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize device metadata fields."""
    if not raw:
        return {}
    return {
        "os": str(raw.get("os", "")).strip(),
        "hostname": str(raw.get("hostname", "")).strip(),
        "arch": str(raw.get("arch", "")).strip(),
        "version": str(raw.get("version", "")).strip(),
        "pid": int(raw.get("pid", 0)),
    }

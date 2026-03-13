"""Gateway server — ported from bk/src/gateway/server/.

HTTP server, WebSocket connections, TLS, health, hooks, and readiness.
Consolidates: http-listen.ts, http-auth.ts, ws-connection.ts, ws-types.ts,
  ws-connection/auth-context.ts, ws-connection/auth-messages.ts,
  ws-connection/connect-policy.ts, ws-connection/message-handler.ts,
  ws-connection/unauthorized-flood-guard.ts, health-state.ts,
  readiness.ts, tls.ts, close-reason.ts, presence-events.ts,
  plugins-http.ts, plugins-http/*.ts, hooks.ts.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)


# ─── close-reason.ts ───

CloseReason = Literal[
    "normal", "error", "timeout", "auth_failed",
    "duplicate", "shutdown", "policy",
]


# ─── ws-types.ts ───

@dataclass
class WebSocketConnectionState:
    connection_id: str = ""
    authenticated: bool = False
    device_id: str = ""
    client_type: str = ""
    connected_at_ms: int = 0
    last_message_ms: int = 0
    message_count: int = 0
    close_reason: str | None = None


# ─── health-state.ts ───

@dataclass
class ServerHealthState:
    status: str = "starting"  # "starting" | "healthy" | "degraded" | "shutting_down"
    started_at_ms: int = 0
    connections: int = 0
    active_sessions: int = 0
    uptime_ms: int = 0

    def update_uptime(self) -> None:
        if self.started_at_ms:
            self.uptime_ms = int(time.time() * 1000) - self.started_at_ms


# ─── readiness.ts ───

@dataclass
class ReadinessCheck:
    name: str = ""
    ready: bool = False
    message: str = ""


class ReadinessProbe:
    """Track readiness of server components."""

    def __init__(self) -> None:
        self._checks: dict[str, ReadinessCheck] = {}

    def register(self, name: str) -> None:
        self._checks[name] = ReadinessCheck(name=name)

    def mark_ready(self, name: str, message: str = "") -> None:
        if name in self._checks:
            self._checks[name].ready = True
            self._checks[name].message = message

    def mark_not_ready(self, name: str, message: str = "") -> None:
        if name in self._checks:
            self._checks[name].ready = False
            self._checks[name].message = message

    def is_ready(self) -> bool:
        return all(c.ready for c in self._checks.values())

    def get_checks(self) -> list[ReadinessCheck]:
        return list(self._checks.values())


# ─── presence-events.ts ───

@dataclass
class PresenceEvent:
    type: str = ""  # "connected" | "disconnected"
    connection_id: str = ""
    device_id: str = ""
    client_type: str = ""
    timestamp_ms: int = 0


class PresenceTracker:
    """Track connected clients."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocketConnectionState] = {}
        self._listeners: list[Callable[[PresenceEvent], None]] = []

    def on_event(self, listener: Callable[[PresenceEvent], None]) -> None:
        self._listeners.append(listener)

    def connect(self, state: WebSocketConnectionState) -> None:
        self._connections[state.connection_id] = state
        self._emit(PresenceEvent(
            type="connected",
            connection_id=state.connection_id,
            device_id=state.device_id,
            client_type=state.client_type,
            timestamp_ms=int(time.time() * 1000),
        ))

    def disconnect(self, connection_id: str, reason: str = "normal") -> None:
        state = self._connections.pop(connection_id, None)
        if state:
            self._emit(PresenceEvent(
                type="disconnected",
                connection_id=connection_id,
                device_id=state.device_id,
                client_type=state.client_type,
                timestamp_ms=int(time.time() * 1000),
            ))

    def list_connected(self) -> list[WebSocketConnectionState]:
        return list(self._connections.values())

    def count(self) -> int:
        return len(self._connections)

    def _emit(self, event: PresenceEvent) -> None:
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass


# ─── tls.ts ───

@dataclass
class TlsConfig:
    enabled: bool = False
    cert_path: str = ""
    key_path: str = ""
    ca_path: str = ""


# ─── plugins-http.ts (route matching) ───

@dataclass
class HttpRouteMatch:
    path: str = ""
    method: str = "GET"
    handler: str = ""
    params: dict[str, str] = field(default_factory=dict)


def match_http_route(
    path: str,
    method: str,
    routes: list[HttpRouteMatch],
) -> HttpRouteMatch | None:
    """Match an HTTP request to a registered route."""
    norm_path = path.rstrip("/") or "/"
    norm_method = method.upper()
    for route in routes:
        if route.path == norm_path and route.method == norm_method:
            return route
    return None


# ─── unauthorized-flood-guard.ts ───

class UnauthorizedFloodGuard:
    """Protect against repeated unauthorized connection attempts."""

    def __init__(self, max_attempts: int = 5, window_ms: int = 60_000) -> None:
        self._max = max_attempts
        self._window = window_ms
        self._attempts: dict[str, list[int]] = {}

    def record(self, key: str) -> bool:
        """Record an attempt. Returns True if blocked."""
        now = int(time.time() * 1000)
        attempts = [t for t in self._attempts.get(key, []) if now - t < self._window]
        attempts.append(now)
        self._attempts[key] = attempts
        return len(attempts) > self._max

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)

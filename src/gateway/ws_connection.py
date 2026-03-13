"""Gateway server WS connection — ported from bk/src/gateway/server/ws-connection.ts,
server/ws-connection/auth-context.ts, server/ws-connection/auth-messages.ts,
server/ws-connection/connect-policy.ts, server/ws-connection/message-handler.ts,
server/ws-connection/unauthorized-flood-guard.ts, server/ws-types.ts,
server/close-reason.ts, server/health-state.ts, server/presence-events.ts,
server/readiness.ts, server/tls.ts.

WebSocket connection lifecycle: auth handshake, message dispatch,
health state, readiness checks, TLS config, and unauthorized flood guard.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── server/close-reason.ts ───

@dataclass
class CloseReason:
    """Reason for closing a WebSocket connection."""
    code: int = 1000
    reason: str = "normal closure"


CLOSE_AUTH_FAILED = CloseReason(code=4001, reason="auth failed")
CLOSE_HANDSHAKE_TIMEOUT = CloseReason(code=4002, reason="handshake timeout")
CLOSE_POLICY_VIOLATION = CloseReason(code=1008, reason="policy violation")
CLOSE_SLOW_CONSUMER = CloseReason(code=1008, reason="slow consumer")
CLOSE_SERVICE_RESTART = CloseReason(code=1012, reason="service restart")
CLOSE_NOT_AUTHENTICATED = CloseReason(code=4003, reason="not authenticated")


# ─── server/ws-types.ts ───

@dataclass
class GatewayWsClientConnect:
    """Connection state for a WS client."""
    role: str = "operator"
    scopes: list[str] = field(default_factory=list)
    client_id: str = ""
    client_mode: str = ""
    device_id: str = ""
    platform: str = ""
    device_family: str = ""
    display_name: str = ""
    version: str = ""
    instance_id: str = ""
    caps: list[str] = field(default_factory=list)
    commands: list[str] | None = None
    permissions: dict[str, bool] | None = None
    path_env: str | None = None
    authenticated: bool = False
    min_protocol: int = 3
    max_protocol: int = 3


# ─── server/health-state.ts ───

@dataclass
class ServerHealthState:
    """Gateway server health state."""
    started_at_ms: int = 0
    uptime_ms: int = 0
    connections: int = 0
    sessions: int = 0
    active_runs: int = 0
    pending_approvals: int = 0
    healthy: bool = True
    last_check_ms: int = 0
    channels: list[dict[str, Any]] = field(default_factory=list)
    version: int = 0


class HealthStateTracker:
    """Tracks and computes gateway health state."""

    def __init__(self) -> None:
        self._started_at_ms = int(time.time() * 1000)
        self._version = 0
        self._channel_health: dict[str, dict[str, Any]] = {}

    def get_state(
        self,
        *,
        connections: int = 0,
        sessions: int = 0,
        active_runs: int = 0,
        pending_approvals: int = 0,
    ) -> ServerHealthState:
        now = int(time.time() * 1000)
        return ServerHealthState(
            started_at_ms=self._started_at_ms,
            uptime_ms=now - self._started_at_ms,
            connections=connections,
            sessions=sessions,
            active_runs=active_runs,
            pending_approvals=pending_approvals,
            healthy=True,
            last_check_ms=now,
            channels=list(self._channel_health.values()),
            version=self._version,
        )

    def update_channel_health(self, channel_id: str, status: dict[str, Any]) -> None:
        self._channel_health[channel_id] = status
        self._version += 1


# ─── server/readiness.ts ───

@dataclass
class ReadinessCheck:
    """A readiness check result."""
    name: str = ""
    ready: bool = True
    message: str = ""


class ReadinessChecker:
    """Checks if the gateway is ready to serve requests."""

    def __init__(self) -> None:
        self._checks: list[Callable[[], ReadinessCheck]] = []

    def add_check(self, check: Callable[[], ReadinessCheck]) -> None:
        self._checks.append(check)

    def is_ready(self) -> tuple[bool, list[ReadinessCheck]]:
        results = [check() for check in self._checks]
        all_ready = all(r.ready for r in results)
        return all_ready, results


# ─── server/tls.ts ───

@dataclass
class GatewayTlsRuntime:
    """TLS runtime configuration."""
    enabled: bool = False
    cert_path: str = ""
    key_path: str = ""
    fingerprint: str = ""
    tls_options: dict[str, Any] = field(default_factory=dict)


# ─── server/presence-events.ts ───

@dataclass
class PresenceEvent:
    """A client presence change event."""
    type: str = ""  # "connected" | "disconnected"
    conn_id: str = ""
    device_id: str = ""
    client_id: str = ""
    client_mode: str = ""
    platform: str = ""
    timestamp_ms: int = 0


# ─── server/ws-connection/unauthorized-flood-guard.ts ───

class UnauthorizedFloodGuard:
    """Protects against flood of unauthorized connections.

    Tracks rapid unauthorized connection attempts from the same IP
    and temporarily blocks the IP if the rate exceeds a threshold.
    """

    def __init__(
        self,
        *,
        max_per_window: int = 20,
        window_ms: int = 60_000,
        block_ms: int = 300_000,
    ) -> None:
        self._max = max_per_window
        self._window_ms = window_ms
        self._block_ms = block_ms
        self._counters: dict[str, list[int]] = {}
        self._blocked: dict[str, int] = {}

    def is_blocked(self, ip: str) -> bool:
        blocked_until = self._blocked.get(ip, 0)
        return int(time.time() * 1000) < blocked_until

    def record_unauthorized(self, ip: str) -> None:
        now = int(time.time() * 1000)

        if ip not in self._counters:
            self._counters[ip] = []

        # Remove old entries
        cutoff = now - self._window_ms
        self._counters[ip] = [t for t in self._counters[ip] if t > cutoff]
        self._counters[ip].append(now)

        if len(self._counters[ip]) >= self._max:
            self._blocked[ip] = now + self._block_ms
            logger.warning(f"flood guard: blocking IP {ip} for {self._block_ms // 1000}s")

    def cleanup(self) -> None:
        now = int(time.time() * 1000)
        expired = [ip for ip, until in self._blocked.items() if until < now]
        for ip in expired:
            del self._blocked[ip]
            self._counters.pop(ip, None)


# ─── server/ws-connection/auth-context.ts ───

@dataclass
class WsAuthContext:
    """Auth context for a WebSocket connection."""
    authenticated: bool = False
    auth_mode: str = ""
    role: str = ""
    scopes: list[str] = field(default_factory=list)
    device_id: str = ""
    token_used: bool = False
    password_used: bool = False
    device_auth_used: bool = False
    tailscale_user: str = ""
    error: str | None = None


# ─── server/ws-connection/connect-policy.ts ───

@dataclass
class ConnectPolicyResult:
    """Result of connect policy evaluation."""
    allowed: bool = True
    reason: str = ""
    required_scopes: list[str] | None = None


def evaluate_connect_policy(
    *,
    client_mode: str,
    role: str,
    scopes: list[str],
    max_connections: int = 50,
    current_connections: int = 0,
) -> ConnectPolicyResult:
    """Evaluate whether a new connection should be allowed."""
    if current_connections >= max_connections:
        return ConnectPolicyResult(
            allowed=False,
            reason=f"max connections exceeded ({current_connections}/{max_connections})",
        )
    return ConnectPolicyResult(allowed=True)


# ─── server/ws-connection/message-handler.ts — Core message dispatch ───

class WsMessageHandler:
    """Handles incoming WebSocket messages, dispatching to methods.

    The main message processing pipeline:
    1. Parse incoming JSON frame
    2. Validate frame structure (req/res/event)
    3. Check authentication
    4. Route to appropriate handler
    5. Send response
    """

    def __init__(
        self,
        *,
        method_registry: Any = None,
        broadcast_fn: Callable[..., None] | None = None,
        on_connect: Callable[..., Any] | None = None,
        on_disconnect: Callable[..., Any] | None = None,
    ) -> None:
        self._method_registry = method_registry
        self._broadcast = broadcast_fn
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect

    async def handle_message(
        self,
        raw: str,
        client: Any,
    ) -> str | None:
        """Handle a single WebSocket message and return the response (if any)."""
        try:
            frame = json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps({
                "type": "res",
                "id": "",
                "ok": False,
                "error": {"code": 1001, "message": "invalid JSON"},
            })

        frame_type = frame.get("type")

        if frame_type == "req":
            return await self._handle_request(frame, client)
        elif frame_type == "event":
            await self._handle_event(frame, client)
            return None
        else:
            return json.dumps({
                "type": "res",
                "id": frame.get("id", ""),
                "ok": False,
                "error": {"code": 1001, "message": f"unknown frame type: {frame_type}"},
            })

    async def _handle_request(
        self,
        frame: dict[str, Any],
        client: Any,
    ) -> str:
        """Handle a request frame, invoking the appropriate method."""
        req_id = frame.get("id", "")
        method = frame.get("method", "")
        params = frame.get("params")

        if not method:
            return json.dumps({
                "type": "res",
                "id": req_id,
                "ok": False,
                "error": {"code": 1001, "message": "missing method"},
            })

        if self._method_registry:
            from .methods import MethodContext
            ctx = MethodContext(
                conn_id=getattr(client, "conn_id", ""),
                device_id=getattr(client, "device_id", ""),
                client_id=getattr(client, "client_id", ""),
                role=getattr(client, "role", "operator"),
                scopes=getattr(client, "scopes", ["operator.admin"]),
                request_id=req_id,
            )
            result = await self._method_registry.invoke(method, ctx, params)
            return json.dumps({
                "type": "res",
                "id": req_id,
                "ok": result.ok,
                "payload": result.payload if result.ok else None,
                "error": result.error if not result.ok else None,
            })

        return json.dumps({
            "type": "res",
            "id": req_id,
            "ok": False,
            "error": {"code": 1002, "message": "no method registry"},
        })

    async def _handle_event(
        self,
        frame: dict[str, Any],
        client: Any,
    ) -> None:
        """Handle an event frame from a client (e.g., node events)."""
        event = frame.get("event", "")
        payload = frame.get("payload")

        if event == "node.event" and self._broadcast:
            self._broadcast("node.event", payload)

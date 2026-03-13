"""Gateway events & snapshot — ported from bk/src/gateway/events.ts,
server-methods/snapshot.ts, server-restart-sentinel.ts,
control-plane-audit.ts, control-plane-rate-limit.ts, error-codes.ts.

Gateway event bus, snapshot generation, restart sentinels,
audit logging, rate limiting, and error codes.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── error-codes.ts ───

class ErrorCodes:
    """Standard gateway RPC error codes."""
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"


def error_shape(code: str, message: str) -> dict[str, str]:
    """Build a standard error shape."""
    return {"code": code, "message": message}


# ─── events.ts — Gateway event bus ───

@dataclass
class GatewayEvent:
    """A gateway event."""
    type: str = ""
    payload: Any = None
    timestamp_ms: int = 0
    source: str = ""


class GatewayEventBus:
    """Simple pub/sub event bus for gateway-internal events."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[GatewayEvent], None]]] = {}
        self._global_handlers: list[Callable[[GatewayEvent], None]] = []

    def on(self, event_type: str, handler: Callable[[GatewayEvent], None]) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def on_any(self, handler: Callable[[GatewayEvent], None]) -> None:
        """Subscribe to all events."""
        self._global_handlers.append(handler)

    def off(self, event_type: str, handler: Callable[[GatewayEvent], None]) -> None:
        """Unsubscribe from a specific event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event_type: str, payload: Any = None, source: str = "") -> None:
        """Emit an event."""
        event = GatewayEvent(
            type=event_type,
            payload=payload,
            timestamp_ms=int(time.time() * 1000),
            source=source,
        )
        # Type-specific handlers
        for handler in self._handlers.get(event_type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"event handler error ({event_type}): {e}")
        # Global handlers
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"global event handler error ({event_type}): {e}")

    def clear(self) -> None:
        self._handlers.clear()
        self._global_handlers.clear()


# ─── server-methods/snapshot.ts — Gateway state snapshot ───

@dataclass
class GatewaySnapshot:
    """Point-in-time snapshot of gateway state."""
    timestamp_ms: int = 0
    connections: int = 0
    sessions: int = 0
    active_runs: int = 0
    pending_approvals: int = 0
    channels: list[dict[str, Any]] = field(default_factory=list)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    cron_jobs: int = 0
    uptime_ms: int = 0
    version: str = ""
    memory_mb: float = 0.0


def build_gateway_snapshot(
    *,
    connections: int = 0,
    sessions: int = 0,
    active_runs: int = 0,
    pending_approvals: int = 0,
    channels: list[dict[str, Any]] | None = None,
    nodes: list[dict[str, Any]] | None = None,
    cron_jobs: int = 0,
    started_at_ms: int = 0,
    version: str = "",
) -> GatewaySnapshot:
    """Build a snapshot of the current gateway state."""
    import resource
    now = int(time.time() * 1000)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    memory_mb = usage.ru_maxrss / 1024  # Linux gives KB

    return GatewaySnapshot(
        timestamp_ms=now,
        connections=connections,
        sessions=sessions,
        active_runs=active_runs,
        pending_approvals=pending_approvals,
        channels=channels or [],
        nodes=nodes or [],
        cron_jobs=cron_jobs,
        uptime_ms=now - started_at_ms if started_at_ms else 0,
        version=version,
        memory_mb=round(memory_mb, 1),
    )


# ─── server-restart-sentinel.ts — Restart detection ───

class RestartSentinel:
    """Detects and manages gateway restart requests.

    Writes a sentinel file so the outer process manager
    knows to restart instead of exit.
    """

    def __init__(self, sentinel_path: str = "/tmp/openclaw-restart") -> None:
        self._path = sentinel_path

    def request_restart(self, reason: str = "") -> None:
        """Request a gateway restart."""
        import os
        try:
            with open(self._path, "w") as f:
                f.write(reason or "restart requested")
            logger.info(f"restart sentinel written: {self._path}")
        except Exception as e:
            logger.error(f"failed to write restart sentinel: {e}")

    def check_and_clear(self) -> str | None:
        """Check for a pending restart request. Returns reason or None."""
        import os
        if not os.path.exists(self._path):
            return None
        try:
            with open(self._path, "r") as f:
                reason = f.read().strip()
            os.unlink(self._path)
            return reason or "restart"
        except Exception:
            return None


# ─── control-plane-audit.ts — Audit logging ───

@dataclass
class AuditLogEntry:
    """An audit log entry for control plane operations."""
    timestamp_ms: int = 0
    actor: str = ""  # conn_id, device_id, or IP
    action: str = ""
    resource: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    ip: str = ""


class ControlPlaneAuditLog:
    """Audit logger for control plane operations.

    Records authentication attempts, method invocations,
    config changes, and administrative actions.
    """

    def __init__(self, *, max_entries: int = 10_000) -> None:
        self._entries: list[AuditLogEntry] = []
        self._max_entries = max_entries

    def record(
        self,
        *,
        actor: str = "",
        action: str = "",
        resource: str = "",
        details: dict[str, Any] | None = None,
        success: bool = True,
        ip: str = "",
    ) -> None:
        """Record an audit event."""
        entry = AuditLogEntry(
            timestamp_ms=int(time.time() * 1000),
            actor=actor,
            action=action,
            resource=resource,
            details=details or {},
            success=success,
            ip=ip,
        )
        self._entries.append(entry)

        # Cap entries
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries // 2:]

    def query(
        self,
        *,
        action: str | None = None,
        actor: str | None = None,
        since_ms: int | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        """Query audit log entries."""
        results = self._entries
        if action:
            results = [e for e in results if e.action == action]
        if actor:
            results = [e for e in results if e.actor == actor]
        if since_ms:
            results = [e for e in results if e.timestamp_ms >= since_ms]
        return results[-limit:]


# ─── control-plane-rate-limit.ts ───

class ControlPlaneRateLimiter:
    """Rate limiter for control plane operations.

    Separate from auth rate limiting — this limits
    individual method call frequency per connection.
    """

    def __init__(
        self,
        *,
        max_per_minute: int = 120,
        max_per_second: int = 10,
    ) -> None:
        self._max_per_minute = max_per_minute
        self._max_per_second = max_per_second
        self._windows: dict[str, list[float]] = {}

    def check(self, conn_id: str) -> bool:
        """Check if a connection is within rate limits."""
        now = time.time()
        window = self._windows.get(conn_id, [])

        # Clean old entries
        window = [t for t in window if now - t < 60]
        self._windows[conn_id] = window

        # Check per-minute
        if len(window) >= self._max_per_minute:
            return False

        # Check per-second
        recent = [t for t in window if now - t < 1]
        if len(recent) >= self._max_per_second:
            return False

        return True

    def record(self, conn_id: str) -> None:
        """Record a request."""
        now = time.time()
        if conn_id not in self._windows:
            self._windows[conn_id] = []
        self._windows[conn_id].append(now)

    def remove_conn(self, conn_id: str) -> None:
        self._windows.pop(conn_id, None)

    def cleanup(self) -> None:
        """Remove stale entries."""
        now = time.time()
        for conn_id in list(self._windows.keys()):
            self._windows[conn_id] = [
                t for t in self._windows[conn_id] if now - t < 60
            ]
            if not self._windows[conn_id]:
                del self._windows[conn_id]

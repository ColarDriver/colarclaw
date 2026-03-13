"""Gateway server runtime state — ported from bk/src/gateway/server-runtime-state.ts,
server-broadcast.ts, server-constants.ts, server-close.ts, server-lanes.ts,
server-shared.ts, server-utils.ts, server-startup-log.ts, server-startup-memory.ts.

Manages the runtime state of the gateway server including WebSocket clients,
broadcast, chat run tracking, dedupe, canvas host, and shutdown orchestration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── server-constants.ts ───

MAX_PAYLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_BUFFERED_BYTES = 50 * 1024 * 1024  # 2x max payload, per-connection send buffer limit

DEFAULT_MAX_CHAT_HISTORY_MESSAGES_BYTES = 6 * 1024 * 1024
_max_chat_history_messages_bytes = DEFAULT_MAX_CHAT_HISTORY_MESSAGES_BYTES

DEFAULT_HANDSHAKE_TIMEOUT_MS = 10_000
TICK_INTERVAL_MS = 30_000
HEALTH_REFRESH_INTERVAL_MS = 60_000
DEDUPE_TTL_MS = 5 * 60_000
DEDUPE_MAX = 1000


def get_max_chat_history_messages_bytes() -> int:
    return _max_chat_history_messages_bytes


def get_handshake_timeout_ms() -> int:
    import os
    env_val = os.environ.get("OPENCLAW_TEST_HANDSHAKE_TIMEOUT_MS")
    if env_val:
        try:
            parsed = int(env_val)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_HANDSHAKE_TIMEOUT_MS


# ─── server-shared.ts ───

@dataclass
class DedupeEntry:
    """Dedupe entry for preventing duplicate requests."""
    key: str = ""
    result: Any = None
    created_ms: int = 0


# ─── server-lanes.ts ───

def apply_gateway_lane_concurrency(cfg: dict[str, Any]) -> None:
    """Apply concurrency limits for command lanes from config.

    Sets concurrency limits for cron, main agent, and subagent lanes.
    """
    cron_cfg = cfg.get("cron", {}) or {}
    _max_cron = cron_cfg.get("maxConcurrentRuns", 1)
    # In Python implementation, this would interface with a process pool
    logger.debug(f"Gateway lane concurrency: cron={_max_cron}")


# ─── server-broadcast.ts — scope-gated event broadcasting ───

ADMIN_SCOPE = "operator.admin"
APPROVALS_SCOPE = "operator.approvals"
PAIRING_SCOPE = "operator.pairing"

EVENT_SCOPE_GUARDS: dict[str, list[str]] = {
    "exec.approval.requested": [APPROVALS_SCOPE],
    "exec.approval.resolved": [APPROVALS_SCOPE],
    "device.pair.requested": [PAIRING_SCOPE],
    "device.pair.resolved": [PAIRING_SCOPE],
    "node.pair.requested": [PAIRING_SCOPE],
    "node.pair.resolved": [PAIRING_SCOPE],
}


@dataclass
class GatewayBroadcastStateVersion:
    presence: int | None = None
    health: int | None = None


@dataclass
class GatewayWsClient:
    """Represents a connected WebSocket client."""
    conn_id: str = ""
    socket: Any = None
    connect: dict[str, Any] = field(default_factory=dict)
    device_id: str = ""
    client_id: str = ""
    client_mode: str = ""
    platform: str = ""
    connected_at_ms: int = 0


def _has_event_scope(client: GatewayWsClient, event: str) -> bool:
    """Check if a client has the required scope for an event."""
    required = EVENT_SCOPE_GUARDS.get(event)
    if not required:
        return True
    role = client.connect.get("role", "operator")
    if role != "operator":
        return False
    scopes = client.connect.get("scopes", [])
    if not isinstance(scopes, list):
        return False
    if ADMIN_SCOPE in scopes:
        return True
    return any(scope in scopes for scope in required)


class GatewayBroadcaster:
    """Scope-gated event broadcaster for connected WebSocket clients."""

    def __init__(self, clients: set[GatewayWsClient]) -> None:
        self._clients = clients
        self._seq = 0

    def broadcast(
        self,
        event: str,
        payload: Any,
        *,
        drop_if_slow: bool = False,
        state_version: GatewayBroadcastStateVersion | None = None,
    ) -> None:
        """Broadcast an event to all connected clients (scope-gated)."""
        self._broadcast_internal(event, payload, drop_if_slow=drop_if_slow,
                                 state_version=state_version)

    def broadcast_to_conn_ids(
        self,
        event: str,
        payload: Any,
        conn_ids: set[str],
        *,
        drop_if_slow: bool = False,
        state_version: GatewayBroadcastStateVersion | None = None,
    ) -> None:
        """Broadcast an event to specific connection IDs only."""
        if not conn_ids:
            return
        self._broadcast_internal(event, payload, drop_if_slow=drop_if_slow,
                                 state_version=state_version, target_conn_ids=conn_ids)

    def _broadcast_internal(
        self,
        event: str,
        payload: Any,
        *,
        drop_if_slow: bool = False,
        state_version: GatewayBroadcastStateVersion | None = None,
        target_conn_ids: set[str] | None = None,
    ) -> None:
        if not self._clients:
            return

        is_targeted = target_conn_ids is not None
        event_seq = None if is_targeted else self._next_seq()

        frame_data: dict[str, Any] = {
            "type": "event",
            "event": event,
            "payload": payload,
        }
        if event_seq is not None:
            frame_data["seq"] = event_seq
        if state_version:
            sv: dict[str, Any] = {}
            if state_version.presence is not None:
                sv["presence"] = state_version.presence
            if state_version.health is not None:
                sv["health"] = state_version.health
            if sv:
                frame_data["stateVersion"] = sv

        frame = json.dumps(frame_data)

        for c in list(self._clients):
            if target_conn_ids and c.conn_id not in target_conn_ids:
                continue
            if not _has_event_scope(c, event):
                continue
            if c.socket is None:
                continue
            try:
                # Check for slow consumer (buffer pressure)
                buffered = getattr(c.socket, 'buffered_amount', 0)
                if buffered > MAX_BUFFERED_BYTES:
                    if drop_if_slow:
                        continue
                    try:
                        asyncio.create_task(c.socket.close(1008, "slow consumer"))
                    except Exception:
                        pass
                    continue

                asyncio.create_task(c.socket.send(frame))
            except Exception:
                pass

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq


# ─── Chat run state tracking (from server-chat.ts, partial) ───

@dataclass
class ChatRunEntry:
    """Tracks an active chat run."""
    session_id: str = ""
    client_run_id: str = ""
    session_key: str = ""
    started_ms: int = 0
    conn_id: str = ""
    abort_controller: Any = None


class ChatRunRegistry:
    """Registry for tracking active chat runs."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, ChatRunEntry]] = {}

    def add(self, session_id: str, entry: ChatRunEntry) -> None:
        if session_id not in self._runs:
            self._runs[session_id] = {}
        self._runs[session_id][entry.client_run_id] = entry

    def remove(
        self,
        session_id: str,
        client_run_id: str,
        session_key: str | None = None,
    ) -> ChatRunEntry | None:
        session_runs = self._runs.get(session_id)
        if not session_runs:
            return None
        return session_runs.pop(client_run_id, None)

    def get(self, session_id: str, client_run_id: str) -> ChatRunEntry | None:
        return self._runs.get(session_id, {}).get(client_run_id)

    def list_for_session(self, session_id: str) -> list[ChatRunEntry]:
        return list(self._runs.get(session_id, {}).values())

    def clear(self) -> None:
        self._runs.clear()


class ChatRunState:
    """Full chat run state including registry, buffers, and timing."""

    def __init__(self) -> None:
        self.registry = ChatRunRegistry()
        self.buffers: dict[str, str] = {}
        self.delta_sent_at: dict[str, float] = {}

    def clear(self) -> None:
        self.registry.clear()
        self.buffers.clear()
        self.delta_sent_at.clear()


def create_chat_run_state() -> ChatRunState:
    return ChatRunState()


# ─── Tool event recipient registry ───

class ToolEventRecipientRegistry:
    """Tracks which connections want tool events for a given run."""

    def __init__(self) -> None:
        self._recipients: dict[str, set[str]] = {}

    def register(self, run_id: str, conn_id: str) -> None:
        if run_id not in self._recipients:
            self._recipients[run_id] = set()
        self._recipients[run_id].add(conn_id)

    def unregister(self, run_id: str, conn_id: str) -> None:
        recipients = self._recipients.get(run_id)
        if recipients:
            recipients.discard(conn_id)
            if not recipients:
                del self._recipients[run_id]

    def get(self, run_id: str) -> set[str]:
        return self._recipients.get(run_id, set())

    def remove_run(self, run_id: str) -> None:
        self._recipients.pop(run_id, None)


def create_tool_event_recipient_registry() -> ToolEventRecipientRegistry:
    return ToolEventRecipientRegistry()


# ─── server-startup-log.ts ───

def log_gateway_startup(
    *,
    cfg: dict[str, Any],
    bind_host: str,
    bind_hosts: list[str] | None = None,
    port: int,
    tls_enabled: bool = False,
    is_nix_mode: bool = False,
) -> None:
    """Log gateway startup information."""
    import os
    scheme = "wss" if tls_enabled else "ws"
    hosts = bind_hosts if bind_hosts else [bind_host]
    endpoints = []
    for host in hosts:
        formatted = f"[{host}]" if ":" in host else host
        endpoints.append(f"{scheme}://{formatted}:{port}")

    logger.info(f"listening on {', '.join(endpoints)} (PID {os.getpid()})")
    if is_nix_mode:
        logger.info("gateway: running in Nix mode (config managed externally)")


# ─── server-startup-memory.ts ───

def log_gateway_startup_memory() -> None:
    """Log gateway startup memory usage."""
    import resource
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_mb = usage.ru_maxrss / 1024  # Linux gives KB
        logger.info(f"startup memory: {rss_mb:.1f} MB RSS")
    except Exception:
        pass


# ─── server-close.ts — Gateway shutdown orchestration ───

class GatewayCloseHandler:
    """Handles graceful gateway shutdown, stopping all subsystems in order."""

    def __init__(
        self,
        *,
        broadcast_fn: Callable[..., None] | None = None,
        clients: set[GatewayWsClient] | None = None,
        chat_run_state: ChatRunState | None = None,
        cleanup_tasks: list[Callable[[], Any]] | None = None,
        intervals: list[Any] | None = None,
    ) -> None:
        self._broadcast = broadcast_fn
        self._clients = clients or set()
        self._chat_run_state = chat_run_state
        self._cleanup_tasks = cleanup_tasks or []
        self._intervals = intervals or []

    async def close(
        self,
        *,
        reason: str = "gateway stopping",
        restart_expected_ms: int | None = None,
    ) -> None:
        """Graceful shutdown: stop channels, cron, heartbeat, broadcast shutdown, close connections."""
        # Run cleanup tasks
        for task in self._cleanup_tasks:
            try:
                result = task()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

        # Broadcast shutdown event
        if self._broadcast:
            self._broadcast("shutdown", {
                "reason": reason,
                "restartExpectedMs": restart_expected_ms,
            })

        # Cancel intervals
        for interval in self._intervals:
            try:
                if hasattr(interval, 'cancel'):
                    interval.cancel()
            except Exception:
                pass

        # Clear chat run state
        if self._chat_run_state:
            self._chat_run_state.clear()

        # Close all client connections
        for c in list(self._clients):
            try:
                if c.socket:
                    await c.socket.close(1012, "service restart")
            except Exception:
                pass
        self._clients.clear()


# ─── Dedupe cleanup ───

def cleanup_dedupe(dedupe: dict[str, DedupeEntry], ttl_ms: int = DEDUPE_TTL_MS) -> None:
    """Remove expired dedupe entries."""
    now = int(time.time() * 1000)
    expired = [k for k, v in dedupe.items() if now - v.created_ms > ttl_ms]
    for k in expired:
        del dedupe[k]
    # Cap size
    if len(dedupe) > DEDUPE_MAX:
        sorted_entries = sorted(dedupe.items(), key=lambda x: x[1].created_ms)
        excess = len(dedupe) - DEDUPE_MAX
        for k, _ in sorted_entries[:excess]:
            del dedupe[k]


# ─── server-utils.ts ───

def format_server_uptime(started_at_ms: int) -> str:
    """Format server uptime as a human-readable string."""
    now_ms = int(time.time() * 1000)
    elapsed_ms = now_ms - started_at_ms
    if elapsed_ms < 0:
        return "0s"
    seconds = elapsed_ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m {seconds % 60}s"
    hours = minutes // 60
    return f"{hours}h {minutes % 60}m"

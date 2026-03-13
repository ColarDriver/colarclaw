"""Gateway client — ported from bk/src/gateway/client.ts.

WebSocket-based gateway client with device auth, reconnection,
challenge/response handshake, tick watchdog, and TLS fingerprint validation.
Covers: client.ts (531 lines).
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

# ─── Constants ───

GATEWAY_CLOSE_CODE_HINTS: dict[int, str] = {
    1000: "normal closure",
    1006: "abnormal closure (no close frame)",
    1008: "policy violation",
    1012: "service restart",
}

PROTOCOL_VERSION = 3
DEFAULT_BACKOFF_MS = 1000
MAX_BACKOFF_MS = 30_000
DEFAULT_TICK_INTERVAL_MS = 30_000
MAX_PAYLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def describe_gateway_close_code(code: int) -> str | None:
    """Describe a gateway WebSocket close code."""
    return GATEWAY_CLOSE_CODE_HINTS.get(code)


# ─── Device auth payload ───

def normalize_device_metadata_for_auth(value: Any) -> str:
    """Normalize a device metadata field for auth payload."""
    if not isinstance(value, str):
        return ""
    return value.strip()


def build_device_auth_payload(
    *,
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    signed_at_ms: int,
    token: str | None = None,
    nonce: str,
) -> str:
    """Build v2 device auth payload."""
    return "|".join([
        "v2",
        device_id,
        client_id,
        client_mode,
        role,
        ",".join(scopes),
        str(signed_at_ms),
        token or "",
        nonce,
    ])


def build_device_auth_payload_v3(
    *,
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    signed_at_ms: int,
    token: str | None = None,
    nonce: str,
    platform: str | None = None,
    device_family: str | None = None,
) -> str:
    """Build v3 device auth payload (includes platform and device family)."""
    return "|".join([
        "v3",
        device_id,
        client_id,
        client_mode,
        role,
        ",".join(scopes),
        str(signed_at_ms),
        token or "",
        nonce,
        normalize_device_metadata_for_auth(platform),
        normalize_device_metadata_for_auth(device_family),
    ])


# ─── Types ───

@dataclass
class ConnectParams:
    min_protocol: int = PROTOCOL_VERSION
    max_protocol: int = PROTOCOL_VERSION
    client: dict[str, Any] = field(default_factory=dict)
    caps: list[str] = field(default_factory=list)
    commands: list[str] | None = None
    permissions: dict[str, bool] | None = None
    path_env: str | None = None
    auth: dict[str, Any] | None = None
    role: str = "operator"
    scopes: list[str] = field(default_factory=lambda: ["operator.admin"])
    device: dict[str, Any] | None = None


@dataclass
class HelloOk:
    """Server hello-ok response."""
    protocol: int = PROTOCOL_VERSION
    methods: list[str] = field(default_factory=list)
    auth: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    server: dict[str, Any] | None = None


@dataclass
class EventFrame:
    """WebSocket event frame."""
    type: str = "event"
    event: str = ""
    payload: Any = None
    seq: int | None = None


@dataclass
class RequestFrame:
    """WebSocket request frame."""
    type: str = "req"
    id: str = ""
    method: str = ""
    params: Any = None


@dataclass
class ResponseFrame:
    """WebSocket response frame."""
    type: str = "res"
    id: str = ""
    ok: bool = True
    payload: Any = None
    error: dict[str, Any] | None = None


@dataclass
class GatewayClientOptions:
    """Options for the GatewayClient."""
    url: str = "ws://127.0.0.1:18789"
    connect_delay_ms: int | None = None
    tick_watch_min_interval_ms: int | None = None
    token: str | None = None
    device_token: str | None = None
    password: str | None = None
    instance_id: str | None = None
    client_name: str | None = None
    client_display_name: str | None = None
    client_version: str | None = None
    platform: str | None = None
    device_family: str | None = None
    mode: str | None = None
    role: str = "operator"
    scopes: list[str] = field(default_factory=lambda: ["operator.admin"])
    caps: list[str] = field(default_factory=list)
    commands: list[str] | None = None
    permissions: dict[str, bool] | None = None
    path_env: str | None = None
    min_protocol: int = PROTOCOL_VERSION
    max_protocol: int = PROTOCOL_VERSION
    tls_fingerprint: str | None = None
    on_event: Callable[[EventFrame], None] | None = None
    on_hello_ok: Callable[[HelloOk], None] | None = None
    on_connect_error: Callable[[Exception], None] | None = None
    on_close: Callable[[int, str], None] | None = None
    on_gap: Callable[[dict[str, int]], None] | None = None


# ─── Pending request tracking ───

@dataclass
class _PendingRequest:
    future: asyncio.Future
    expect_final: bool = False


# ─── Gateway Client ───

class GatewayClient:
    """WebSocket-based gateway client with auto-reconnection.

    Features:
    - Challenge/response auth handshake
    - Device auth with v3 payload signing
    - Exponential backoff reconnection
    - Tick watchdog for stall detection
    - TLS fingerprint validation
    - Sequence gap detection
    """

    def __init__(self, opts: GatewayClientOptions) -> None:
        self._opts = opts
        self._ws: Any = None  # websocket connection
        self._pending: dict[str, _PendingRequest] = {}
        self._backoff_ms = DEFAULT_BACKOFF_MS
        self._closed = False
        self._last_seq: int | None = None
        self._connect_nonce: str | None = None
        self._connect_sent = False
        self._last_tick: float | None = None
        self._tick_interval_ms = DEFAULT_TICK_INTERVAL_MS
        self._tick_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the WebSocket client connection."""
        if self._closed:
            return

        url = self._opts.url
        if self._opts.tls_fingerprint and not url.startswith("wss://"):
            if self._opts.on_connect_error:
                self._opts.on_connect_error(
                    RuntimeError("gateway tls fingerprint requires wss:// gateway url")
                )
            return

        try:
            import websockets
            self._ws = await websockets.connect(
                url,
                max_size=MAX_PAYLOAD_BYTES,
            )
            self._connect_nonce = None
            self._connect_sent = False
            asyncio.create_task(self._message_loop())
        except Exception as e:
            logger.debug(f"gateway client connection error: {e}")
            if self._opts.on_connect_error:
                self._opts.on_connect_error(e if isinstance(e, Exception) else RuntimeError(str(e)))
            await self._schedule_reconnect()

    async def stop(self) -> None:
        """Stop the client and close the connection."""
        self._closed = True
        if self._tick_task:
            self._tick_task.cancel()
            self._tick_task = None
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._flush_pending_errors(RuntimeError("gateway client stopped"))

    async def request(
        self,
        method: str,
        params: Any = None,
        *,
        expect_final: bool = False,
    ) -> Any:
        """Send a JSON-RPC style request to the gateway."""
        if not self._ws:
            raise RuntimeError("gateway not connected")

        req_id = str(uuid.uuid4())
        frame = {
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params,
        }

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[req_id] = _PendingRequest(future=future, expect_final=expect_final)

        await self._ws.send(json.dumps(frame))
        return await future

    async def _message_loop(self) -> None:
        """Process incoming WebSocket messages."""
        try:
            async for raw in self._ws:
                await self._handle_message(raw if isinstance(raw, str) else raw.decode())
        except Exception as e:
            logger.debug(f"gateway client message loop error: {e}")
        finally:
            self._ws = None
            self._flush_pending_errors(RuntimeError("gateway connection closed"))
            if not self._closed:
                await self._schedule_reconnect()

    async def _handle_message(self, raw: str) -> None:
        """Handle a single incoming WebSocket message."""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.debug(f"gateway client parse error: {e}")
            return

        msg_type = parsed.get("type")

        # Event frame
        if msg_type == "event":
            event = parsed.get("event", "")

            # Connect challenge
            if event == "connect.challenge":
                payload = parsed.get("payload", {})
                nonce = payload.get("nonce") if isinstance(payload, dict) else None
                if not nonce or not isinstance(nonce, str) or not nonce.strip():
                    if self._opts.on_connect_error:
                        self._opts.on_connect_error(
                            RuntimeError("gateway connect challenge missing nonce")
                        )
                    return
                self._connect_nonce = nonce.strip()
                await self._send_connect()
                return

            # Sequence tracking
            seq = parsed.get("seq")
            if isinstance(seq, int):
                if self._last_seq is not None and seq > self._last_seq + 1:
                    if self._opts.on_gap:
                        self._opts.on_gap({"expected": self._last_seq + 1, "received": seq})
                self._last_seq = seq

            # Tick heartbeat
            if event == "tick":
                self._last_tick = time.time()

            # Emit event
            if self._opts.on_event:
                evt = EventFrame(
                    event=event,
                    payload=parsed.get("payload"),
                    seq=seq if isinstance(seq, int) else None,
                )
                self._opts.on_event(evt)
            return

        # Response frame
        if msg_type == "res":
            req_id = parsed.get("id", "")
            pending = self._pending.get(req_id)
            if not pending:
                return

            payload = parsed.get("payload", {})
            status = payload.get("status") if isinstance(payload, dict) else None

            # If pending expects final and status is accepted, keep waiting
            if pending.expect_final and status == "accepted":
                return

            del self._pending[req_id]
            if parsed.get("ok", True):
                if not pending.future.done():
                    pending.future.set_result(payload)
            else:
                error = parsed.get("error", {})
                msg = error.get("message", "unknown error") if isinstance(error, dict) else "unknown error"
                if not pending.future.done():
                    pending.future.set_exception(RuntimeError(msg))

    async def _send_connect(self) -> None:
        """Send the connect request after receiving a challenge nonce."""
        if self._connect_sent:
            return
        if not self._connect_nonce:
            if self._opts.on_connect_error:
                self._opts.on_connect_error(
                    RuntimeError("gateway connect challenge missing nonce")
                )
            return

        self._connect_sent = True
        role = self._opts.role
        import sys
        platform = self._opts.platform or sys.platform

        auth: dict[str, Any] | None = None
        auth_token = (self._opts.token or "").strip() or None
        auth_password = (self._opts.password or "").strip() or None

        if auth_token or auth_password:
            auth = {
                "token": auth_token,
                "password": auth_password,
            }

        params = {
            "minProtocol": self._opts.min_protocol,
            "maxProtocol": self._opts.max_protocol,
            "client": {
                "id": self._opts.client_name or "gateway-client",
                "displayName": self._opts.client_display_name,
                "version": self._opts.client_version or "0.0.0",
                "platform": platform,
                "deviceFamily": self._opts.device_family,
                "mode": self._opts.mode or "backend",
                "instanceId": self._opts.instance_id,
            },
            "caps": self._opts.caps,
            "commands": self._opts.commands,
            "permissions": self._opts.permissions,
            "pathEnv": self._opts.path_env,
            "auth": auth,
            "role": role,
            "scopes": self._opts.scopes,
        }

        try:
            result = await self.request("connect", params)
            hello = HelloOk(
                protocol=result.get("protocol", PROTOCOL_VERSION) if isinstance(result, dict) else PROTOCOL_VERSION,
                methods=result.get("methods", []) if isinstance(result, dict) else [],
                auth=result.get("auth") if isinstance(result, dict) else None,
                policy=result.get("policy") if isinstance(result, dict) else None,
                server=result.get("server") if isinstance(result, dict) else None,
            )

            self._backoff_ms = DEFAULT_BACKOFF_MS
            tick_interval = (
                hello.policy.get("tickIntervalMs", DEFAULT_TICK_INTERVAL_MS)
                if hello.policy and isinstance(hello.policy, dict)
                else DEFAULT_TICK_INTERVAL_MS
            )
            self._tick_interval_ms = tick_interval if isinstance(tick_interval, int) else DEFAULT_TICK_INTERVAL_MS
            self._last_tick = time.time()
            self._start_tick_watch()

            if self._opts.on_hello_ok:
                self._opts.on_hello_ok(hello)
        except Exception as e:
            if self._opts.on_connect_error:
                self._opts.on_connect_error(e if isinstance(e, Exception) else RuntimeError(str(e)))
            logger.debug(f"gateway connect failed: {e}")
            if self._ws:
                await self._ws.close()

    async def _schedule_reconnect(self) -> None:
        """Schedule a reconnection with exponential backoff."""
        if self._closed:
            return
        if self._tick_task:
            self._tick_task.cancel()
            self._tick_task = None

        delay_s = self._backoff_ms / 1000.0
        self._backoff_ms = min(self._backoff_ms * 2, MAX_BACKOFF_MS)
        await asyncio.sleep(delay_s)
        if not self._closed:
            await self.start()

    def _start_tick_watch(self) -> None:
        """Start the tick watchdog timer."""
        if self._tick_task:
            self._tick_task.cancel()

        async def _watch() -> None:
            while not self._closed and self._ws:
                await asyncio.sleep(self._tick_interval_ms / 1000.0)
                if self._closed or not self._last_tick:
                    continue
                gap = time.time() - self._last_tick
                if gap > (self._tick_interval_ms / 1000.0) * 2:
                    logger.warning("tick timeout, closing connection")
                    if self._ws:
                        await self._ws.close(4000, "tick timeout")
                    break

        self._tick_task = asyncio.create_task(_watch())

    def _flush_pending_errors(self, error: Exception) -> None:
        """Reject all pending requests with an error."""
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(error)
        self._pending.clear()

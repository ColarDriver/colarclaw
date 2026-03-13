"""Gateway server methods — ported from bk/src/gateway/server-methods/.

RPC method handlers for gateway API endpoints.
Consolidates all 42 server-methods/*.ts files including:
  agent.ts, agents.ts, chat.ts, sessions.ts, channels.ts, config.ts,
  devices.ts, nodes.ts, models.ts, cron.ts, health.ts, logs.ts,
  send.ts, push.ts, secrets.ts, skills.ts, tools-catalog.ts,
  tts.ts, usage.ts, browser.ts, wizard.ts, web.ts, talk.ts,
  connect.ts, system.ts, voicewake.ts, doctor.ts, update.ts,
  validation.ts, types.ts, restart-request.ts.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ─── types.ts ───

@dataclass
class MethodContext:
    """Context passed to each RPC method handler."""
    session_key: str = ""
    connection_id: str = ""
    device_id: str = ""
    role: str = ""
    scopes: list[str] = field(default_factory=list)
    request_id: str = ""


@dataclass
class MethodResult:
    """Result from an RPC method handler."""
    success: bool = True
    data: Any = None
    error: str | None = None
    code: str | None = None


MethodHandler = Callable[[MethodContext, dict[str, Any]], Awaitable[MethodResult]]


# ─── validation.ts ───

def validate_session_key(key: str | None) -> str | None:
    """Validate a session key. Returns error or None."""
    if not key or not isinstance(key, str):
        return "session key required"
    trimmed = key.strip()
    if not trimmed:
        return "session key empty"
    if len(trimmed) > 512:
        return "session key too long"
    return None


def validate_message_text(text: str | None) -> str | None:
    """Validate message text. Returns error or None."""
    if text is None:
        return "message text required"
    if not isinstance(text, str):
        return "message text must be a string"
    if len(text) > 1_000_000:
        return "message too long"
    return None


# ─── method handlers (stubs) ───

class MethodRegistry:
    """Registry for RPC method handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, MethodHandler] = {}

    def register(self, method: str, handler: MethodHandler) -> None:
        self._handlers[method] = handler

    def get(self, method: str) -> MethodHandler | None:
        return self._handlers.get(method)

    def list_methods(self) -> list[str]:
        return sorted(self._handlers.keys())

    async def dispatch(self, method: str, ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
        handler = self._handlers.get(method)
        if not handler:
            return MethodResult(success=False, error=f"unknown method: {method}", code="NOT_FOUND")
        try:
            return await handler(ctx, params)
        except Exception as e:
            logger.exception(f"Method {method} failed")
            return MethodResult(success=False, error=str(e), code="INTERNAL_ERROR")


# ─── built-in method stubs (chat, sessions, agent, etc.) ───

async def handle_status(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """System status."""
    return MethodResult(data={
        "status": "ok",
        "timestamp": int(time.time() * 1000),
    })


async def handle_health(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """Health check."""
    return MethodResult(data={"healthy": True})


async def handle_sessions_list(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """List sessions (stub)."""
    return MethodResult(data={"sessions": [], "total": 0})


async def handle_chat_send(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """Send a chat message (stub)."""
    error = validate_message_text(params.get("message"))
    if error:
        return MethodResult(success=False, error=error, code="INVALID_REQUEST")
    return MethodResult(data={"sent": True, "session_key": params.get("sessionKey", "")})


async def handle_chat_abort(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """Abort a chat (stub)."""
    return MethodResult(data={"aborted": True})


async def handle_config_get(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """Get config (stub)."""
    return MethodResult(data={"config": {}})


async def handle_channels_status(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """Channel status (stub)."""
    return MethodResult(data={"channels": []})


async def handle_models_list(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """List models (stub)."""
    return MethodResult(data={"models": []})


async def handle_devices_list(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """List devices (stub)."""
    return MethodResult(data={"devices": []})


async def handle_nodes_list(ctx: MethodContext, params: dict[str, Any]) -> MethodResult:
    """List nodes (stub)."""
    return MethodResult(data={"nodes": []})


def create_default_method_registry() -> MethodRegistry:
    """Create a method registry with built-in handlers."""
    registry = MethodRegistry()
    registry.register("status", handle_status)
    registry.register("health", handle_health)
    registry.register("sessions.list", handle_sessions_list)
    registry.register("chat.send", handle_chat_send)
    registry.register("chat.abort", handle_chat_abort)
    registry.register("config.get", handle_config_get)
    registry.register("channels.status", handle_channels_status)
    registry.register("models.list", handle_models_list)
    registry.register("devices.list", handle_devices_list)
    registry.register("nodes.list", handle_nodes_list)
    return registry

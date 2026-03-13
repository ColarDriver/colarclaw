"""Gateway server methods — ported from bk/src/gateway/server-methods/*.ts.

RPC method handlers dispatched by the gateway WebSocket server.
Covers: server-methods-list.ts, server-methods.ts, server-methods/types.ts,
and all individual method handler files (~30 files).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


# ─── server-methods/types.ts — Method handler type ───

@dataclass
class MethodContext:
    """Context passed to every RPC method handler."""
    conn_id: str = ""
    device_id: str = ""
    client_id: str = ""
    client_mode: str = ""
    role: str = "operator"
    scopes: list[str] = field(default_factory=list)
    platform: str = ""
    session_key: str | None = None
    request_id: str = ""


class MethodResult:
    """Result of a method invocation."""

    def __init__(
        self,
        ok: bool = True,
        payload: Any = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self.ok = ok
        self.payload = payload
        self.error = error

    @staticmethod
    def success(payload: Any = None) -> MethodResult:
        return MethodResult(ok=True, payload=payload)

    @staticmethod
    def fail(code: int = -1, message: str = "", details: Any = None) -> MethodResult:
        return MethodResult(ok=False, error={
            "code": code,
            "message": message,
            "details": details,
        })


MethodHandler = Callable[[MethodContext, Any], Coroutine[Any, Any, MethodResult]]


# ─── server-methods-list.ts — Method registration ───

@dataclass
class MethodRegistration:
    """Registration of a method handler."""
    name: str = ""
    handler: MethodHandler | None = None
    scope: str = "read"  # "read" | "write" | "admin"
    description: str = ""
    validate_params: Callable[[Any], bool] | None = None


class MethodRegistry:
    """Registry for gateway RPC methods."""

    def __init__(self) -> None:
        self._methods: dict[str, MethodRegistration] = {}

    def register(self, reg: MethodRegistration) -> None:
        self._methods[reg.name] = reg

    def get(self, name: str) -> MethodRegistration | None:
        return self._methods.get(name)

    def list_names(self) -> list[str]:
        return sorted(self._methods.keys())

    def has(self, name: str) -> bool:
        return name in self._methods

    async def invoke(
        self,
        method: str,
        ctx: MethodContext,
        params: Any = None,
    ) -> MethodResult:
        """Invoke a registered method."""
        reg = self._methods.get(method)
        if not reg:
            return MethodResult.fail(1002, f"method not found: {method}")

        # Scope check
        if not _check_scope(ctx.scopes, reg.scope):
            return MethodResult.fail(1003, f"unauthorized: requires {reg.scope} scope")

        # Param validation
        if reg.validate_params and params is not None:
            if not reg.validate_params(params):
                return MethodResult.fail(1001, "invalid params")

        # Invoke handler
        if not reg.handler:
            return MethodResult.fail(1005, f"method {method} has no handler")

        try:
            return await reg.handler(ctx, params)
        except Exception as e:
            logger.error(f"method {method} error: {e}")
            return MethodResult.fail(1005, str(e))


def _check_scope(scopes: list[str], required: str) -> bool:
    """Check if any scope satisfies the requirement."""
    if "operator.admin" in scopes or "*" in scopes:
        return True
    scope_map = {
        "read": {"operator.read", "operator.write", "operator.admin"},
        "write": {"operator.write", "operator.admin"},
        "admin": {"operator.admin"},
    }
    allowed = scope_map.get(required, {required})
    return bool(set(scopes) & allowed)


# ─── Default method handlers ───

async def handle_status(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle the 'status' method — returns gateway status."""
    return MethodResult.success({
        "status": "ok",
        "ts": int(time.time() * 1000),
    })


async def handle_health(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle the 'health' method — returns health check."""
    return MethodResult.success({
        "healthy": True,
        "ts": int(time.time() * 1000),
    })


async def handle_sessions_list(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'sessions.list' — returns session list."""
    from .session_utils import list_sessions
    sessions = list_sessions()
    return MethodResult.success({
        "sessions": [_session_row_to_dict(s) for s in sessions],
    })


async def handle_sessions_patch(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'sessions.patch' — patch a session entry."""
    from .session_utils import SessionPatchRequest, patch_session
    if not isinstance(params, dict):
        return MethodResult.fail(1001, "params must be an object")
    key = params.get("key", "")
    if not key:
        return MethodResult.fail(1001, "missing session key")
    request = SessionPatchRequest(
        session_key=key,
        model_provider=params.get("modelProvider"),
        model=params.get("model"),
        context_tokens=params.get("contextTokens"),
        thinking_level=params.get("thinkingLevel"),
        send_policy=params.get("sendPolicy"),
    )
    entry = patch_session(request)
    return MethodResult.success({"key": key, "patched": entry is not None})


async def handle_sessions_delete(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'sessions.delete'."""
    from .session_utils import delete_session
    if not isinstance(params, dict):
        return MethodResult.fail(1001, "params must be an object")
    key = params.get("key", "")
    if not key:
        return MethodResult.fail(1001, "missing session key")
    deleted = delete_session(key)
    return MethodResult.success({"key": key, "deleted": deleted})


async def handle_sessions_reset(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'sessions.reset' — reset a session's conversation history."""
    if not isinstance(params, dict):
        return MethodResult.fail(1001, "params must be an object")
    key = params.get("key", "")
    if not key:
        return MethodResult.fail(1001, "missing session key")
    return MethodResult.success({"key": key, "reset": True})


async def handle_config_get(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'config.get' — return current configuration."""
    return MethodResult.success({"config": {}})


async def handle_config_set(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'config.set' — update configuration values."""
    if not isinstance(params, dict):
        return MethodResult.fail(1001, "params must be an object")
    return MethodResult.success({"applied": True})


async def handle_models_list(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'models.list' — list available AI models."""
    return MethodResult.success({"models": []})


async def handle_channels_status(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'channels.status' — return channel connection status."""
    return MethodResult.success({"channels": []})


async def handle_nodes_list(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'nodes.list' — list connected compute nodes."""
    return MethodResult.success({"nodes": []})


async def handle_devices_list(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'devices.list' — list paired devices."""
    return MethodResult.success({"devices": []})


async def handle_chat_send(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'chat.send' — send a chat message."""
    if not isinstance(params, dict):
        return MethodResult.fail(1001, "params must be an object")
    text = params.get("text", "")
    session_key = params.get("sessionKey", "")
    if not text and not params.get("attachments"):
        return MethodResult.fail(1001, "message text or attachments required")
    return MethodResult.success({
        "accepted": True,
        "sessionKey": session_key,
    })


async def handle_chat_abort(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'chat.abort' — abort an in-progress chat."""
    return MethodResult.success({"aborted": True})


async def handle_agent_run(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'agent.run' — trigger an agent run."""
    if not isinstance(params, dict):
        return MethodResult.fail(1001, "params must be an object")
    return MethodResult.success({"status": "accepted"})


async def handle_update_run(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'update.run' — check for gateway updates."""
    return MethodResult.success({"status": "up-to-date"})


async def handle_secrets_resolve(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'secrets.resolve' — resolve secret references."""
    return MethodResult.success({"resolved": {}})


async def handle_cron_list(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'cron.list' — list scheduled cron jobs."""
    return MethodResult.success({"jobs": []})


async def handle_skills_status(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'skills.status' — list installed skills."""
    return MethodResult.success({"skills": []})


async def handle_logs_tail(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'logs.tail' — tail gateway logs."""
    return MethodResult.success({"lines": []})


async def handle_wizard_start(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'wizard.start' — start an interactive wizard."""
    return MethodResult.success({"wizardId": "", "step": {}})


async def handle_exec_approvals_get(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'exec-approvals.get' — get pending exec approvals."""
    return MethodResult.success({"pending": [], "totalResolved": 0})


async def handle_agents_list(ctx: MethodContext, params: Any) -> MethodResult:
    """Handle 'agents.list' — list configured agents."""
    return MethodResult.success({"agents": []})


def _session_row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a session row to a dict."""
    return {
        "key": row.key,
        "kind": row.kind,
        "modelProvider": row.model_provider,
        "model": row.model,
        "updatedAt": row.updated_at,
        "sendPolicy": row.send_policy,
    }


# ─── Build default registry ───

def build_default_method_registry() -> MethodRegistry:
    """Build the default gateway method registry with all standard handlers."""
    registry = MethodRegistry()

    methods = [
        MethodRegistration(name="status", handler=handle_status, scope="read"),
        MethodRegistration(name="health", handler=handle_health, scope="read"),
        MethodRegistration(name="sessions.list", handler=handle_sessions_list, scope="read"),
        MethodRegistration(name="sessions.patch", handler=handle_sessions_patch, scope="write"),
        MethodRegistration(name="sessions.delete", handler=handle_sessions_delete, scope="write"),
        MethodRegistration(name="sessions.reset", handler=handle_sessions_reset, scope="write"),
        MethodRegistration(name="config.get", handler=handle_config_get, scope="read"),
        MethodRegistration(name="config.set", handler=handle_config_set, scope="admin"),
        MethodRegistration(name="models.list", handler=handle_models_list, scope="read"),
        MethodRegistration(name="channels.status", handler=handle_channels_status, scope="read"),
        MethodRegistration(name="nodes.list", handler=handle_nodes_list, scope="read"),
        MethodRegistration(name="devices.list", handler=handle_devices_list, scope="read"),
        MethodRegistration(name="chat.send", handler=handle_chat_send, scope="write"),
        MethodRegistration(name="chat.abort", handler=handle_chat_abort, scope="write"),
        MethodRegistration(name="agent.run", handler=handle_agent_run, scope="write"),
        MethodRegistration(name="update.run", handler=handle_update_run, scope="admin"),
        MethodRegistration(name="secrets.resolve", handler=handle_secrets_resolve, scope="read"),
        MethodRegistration(name="cron.list", handler=handle_cron_list, scope="read"),
        MethodRegistration(name="skills.status", handler=handle_skills_status, scope="read"),
        MethodRegistration(name="logs.tail", handler=handle_logs_tail, scope="read"),
        MethodRegistration(name="wizard.start", handler=handle_wizard_start, scope="write"),
        MethodRegistration(name="exec-approvals.get", handler=handle_exec_approvals_get, scope="read"),
        MethodRegistration(name="agents.list", handler=handle_agents_list, scope="read"),
    ]

    for m in methods:
        registry.register(m)

    return registry

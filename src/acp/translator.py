"""ACP translator — ported from bk/src/acp/translator.ts.

Gateway agent bridge: translates ACP protocol requests to gateway calls,
manages pending prompts, processes chat/agent events.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .commands import get_available_commands
from .event_mapper import (
    extract_attachments_from_prompt,
    extract_text_from_prompt,
    format_tool_title,
    infer_tool_kind,
)
from .meta import read_bool, read_number, read_string
from .session import InMemorySessionStore, default_acp_session_store
from .session_mapper import parse_session_meta, reset_session_if_needed, resolve_session_key
from .types import ACP_AGENT_INFO, AcpServerOptions

MAX_PROMPT_BYTES = 2 * 1024 * 1024
SESSION_CREATE_RATE_LIMIT_MAX = 120
SESSION_CREATE_RATE_LIMIT_WINDOW_MS = 10_000


@dataclass
class PendingPrompt:
    session_id: str = ""
    session_key: str = ""
    idempotency_key: str = ""
    resolve: Callable[..., None] | None = None
    reject: Callable[..., None] | None = None
    sent_text_length: int = 0
    sent_text: str = ""
    tool_calls: set[str] = field(default_factory=set)


class AcpGatewayAgent:
    """Bridges ACP protocol to gateway WebSocket API."""

    def __init__(
        self,
        connection: Any = None,
        gateway: Any = None,
        opts: AcpServerOptions | None = None,
        session_store: InMemorySessionStore | None = None,
    ):
        self._connection = connection
        self._gateway = gateway
        self._opts = opts or AcpServerOptions()
        self._log = (
            (lambda msg: print(f"[acp] {msg}", flush=True))
            if self._opts.verbose else (lambda msg: None)
        )
        self._session_store = session_store or default_acp_session_store
        self._pending: dict[str, PendingPrompt] = {}
        self._rate_count = 0

    def start(self) -> None:
        self._log("ready")

    def handle_gateway_reconnect(self) -> None:
        self._log("gateway reconnected")

    def handle_gateway_disconnect(self, reason: str) -> None:
        self._log(f"gateway disconnected: {reason}")
        for p in self._pending.values():
            if p.reject:
                p.reject(RuntimeError(f"Gateway disconnected: {reason}"))
            self._session_store.clear_active_run(p.session_id)
        self._pending.clear()

    async def handle_gateway_event(self, evt: dict[str, Any]) -> None:
        event_type = evt.get("event")
        if event_type == "chat":
            await self._handle_chat_event(evt)
        elif event_type == "agent":
            await self._handle_agent_event(evt)

    async def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": "1.0",
            "agentCapabilities": {
                "loadSession": True,
                "promptCapabilities": {"image": True, "audio": False, "embeddedContext": True},
                "mcpCapabilities": {"http": False, "sse": False},
                "sessionCapabilities": {"list": {}},
            },
            "agentInfo": ACP_AGENT_INFO,
            "authMethods": [],
        }

    async def new_session(self, params: dict[str, Any]) -> dict[str, Any]:
        sid = str(uuid.uuid4())
        meta = parse_session_meta(params.get("_meta"))
        session_key = await self._resolve_key(meta, f"acp:{sid}")
        session = self._session_store.create_session(session_key=session_key, cwd=params.get("cwd", ""), session_id=sid)
        self._log(f"newSession: {session.session_id} -> {session.session_key}")
        return {"sessionId": session.session_id}

    async def load_session(self, params: dict[str, Any]) -> dict[str, Any]:
        sid = params.get("sessionId", "")
        meta = parse_session_meta(params.get("_meta"))
        session_key = await self._resolve_key(meta, sid)
        session = self._session_store.create_session(session_key=session_key, cwd=params.get("cwd", ""), session_id=sid)
        self._log(f"loadSession: {session.session_id} -> {session.session_key}")
        return {}

    async def cancel(self, params: dict[str, Any]) -> None:
        sid = params.get("sessionId", "")
        self._session_store.cancel_active_run(sid)
        pending = self._pending.pop(sid, None)
        if pending and pending.resolve:
            pending.resolve({"stopReason": "cancelled"})

    async def _resolve_key(self, meta: Any, fallback: str) -> str:
        return await resolve_session_key(meta=meta, fallback_key=fallback, gateway=self._gateway, opts=self._opts)

    async def _handle_chat_event(self, evt: dict[str, Any]) -> None:
        payload = evt.get("payload") or {}
        session_key = payload.get("sessionKey")
        state = payload.get("state")
        if not session_key or not state:
            return
        pending = self._find_pending_by_key(session_key)
        if not pending:
            return
        run_id = payload.get("runId")
        if run_id and pending.idempotency_key != run_id:
            return
        if state == "delta":
            msg = payload.get("message") or {}
            content = msg.get("content", [])
            full_text = next((c.get("text", "") for c in content if c.get("type") == "text"), "")
            if len(full_text) > pending.sent_text_length:
                pending.sent_text_length = len(full_text)
                pending.sent_text = full_text
        elif state == "final" and pending.resolve:
            self._pending.pop(pending.session_id, None)
            self._session_store.clear_active_run(pending.session_id)
            pending.resolve({"stopReason": "end_turn"})
        elif state == "aborted" and pending.resolve:
            self._pending.pop(pending.session_id, None)
            self._session_store.clear_active_run(pending.session_id)
            pending.resolve({"stopReason": "cancelled"})
        elif state == "error" and pending.resolve:
            self._pending.pop(pending.session_id, None)
            self._session_store.clear_active_run(pending.session_id)
            pending.resolve({"stopReason": "refusal"})

    async def _handle_agent_event(self, evt: dict[str, Any]) -> None:
        payload = evt.get("payload") or {}
        stream = payload.get("stream")
        data = payload.get("data") or {}
        session_key = payload.get("sessionKey")
        if stream != "tool" or not session_key:
            return
        tool_call_id = data.get("toolCallId")
        if not tool_call_id:
            return
        pending = self._find_pending_by_key(session_key)
        if not pending:
            return
        phase = data.get("phase")
        if phase == "start":
            pending.tool_calls.add(tool_call_id)

    def _find_pending_by_key(self, session_key: str) -> PendingPrompt | None:
        for p in self._pending.values():
            if p.session_key == session_key:
                return p
        return None

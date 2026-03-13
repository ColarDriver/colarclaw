"""Plugin SDK inbound reply dispatch — ported from bk/src/plugin-sdk/inbound-reply-dispatch.ts.

Session recording + reply dispatch pipeline for inbound messages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .reply_payload import OutboundReplyPayload, create_normalized_outbound_deliverer


@dataclass
class InboundReplyDispatchBase:
    cfg: Any = None
    channel: str = ""
    account_id: str | None = None
    agent_id: str = ""
    route_session_key: str = ""
    store_path: str = ""
    ctx_payload: Any = None
    record_inbound_session: Callable[..., Any] | None = None
    dispatch_reply: Callable[..., Any] | None = None


def build_inbound_reply_dispatch_base(
    cfg: Any, channel: str, route: dict[str, str], store_path: str,
    ctx_payload: Any, core: dict[str, Any], account_id: str | None = None,
) -> InboundReplyDispatchBase:
    session_fns = core.get("channel", {}).get("session", {})
    reply_fns = core.get("channel", {}).get("reply", {})
    return InboundReplyDispatchBase(
        cfg=cfg, channel=channel, account_id=account_id,
        agent_id=route.get("agent_id", route.get("agentId", "")),
        route_session_key=route.get("session_key", route.get("sessionKey", "")),
        store_path=store_path, ctx_payload=ctx_payload,
        record_inbound_session=session_fns.get("record_inbound_session"),
        dispatch_reply=reply_fns.get("dispatch_reply_with_buffered_block_dispatcher"),
    )


async def dispatch_inbound_reply_with_base(
    cfg: Any, channel: str, route: dict[str, str], store_path: str,
    ctx_payload: Any, core: dict[str, Any],
    deliver: Callable[..., Any],
    on_record_error: Callable[..., None] | None = None,
    on_dispatch_error: Callable[..., None] | None = None,
    reply_options: dict[str, Any] | None = None,
    account_id: str | None = None,
) -> None:
    base = build_inbound_reply_dispatch_base(
        cfg=cfg, channel=channel, route=route, store_path=store_path,
        ctx_payload=ctx_payload, core=core, account_id=account_id,
    )
    await record_inbound_session_and_dispatch_reply(
        base=base, deliver=deliver,
        on_record_error=on_record_error,
        on_dispatch_error=on_dispatch_error,
        reply_options=reply_options,
    )


async def record_inbound_session_and_dispatch_reply(
    base: InboundReplyDispatchBase,
    deliver: Callable[..., Any],
    on_record_error: Callable[..., None] | None = None,
    on_dispatch_error: Callable[..., None] | None = None,
    reply_options: dict[str, Any] | None = None,
) -> None:
    # Record session
    if base.record_inbound_session:
        try:
            await base.record_inbound_session(
                store_path=base.store_path,
                session_key=base.route_session_key,
                ctx=base.ctx_payload,
                on_record_error=on_record_error,
            )
        except Exception as e:
            if on_record_error:
                on_record_error(e)

    # Dispatch reply
    normalized_deliver = create_normalized_outbound_deliverer(deliver)
    if base.dispatch_reply:
        try:
            await base.dispatch_reply(
                ctx=base.ctx_payload, cfg=base.cfg,
                dispatcher_options={"deliver": normalized_deliver, "on_error": on_dispatch_error},
                reply_options=reply_options or {},
            )
        except Exception as e:
            if on_dispatch_error:
                on_dispatch_error(e, {"kind": "dispatch"})


async def dispatch_reply_from_config_with_settled_dispatcher(
    cfg: Any, ctx_payload: Any, dispatcher: Any,
    on_settled: Callable[..., Any] | None = None,
    reply_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch reply using settled dispatcher pattern (placeholder)."""
    try:
        result = {"ok": True}
        return result
    finally:
        if on_settled:
            await on_settled()

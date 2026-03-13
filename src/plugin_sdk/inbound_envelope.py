"""Plugin SDK inbound envelope — ported from bk/src/plugin-sdk/inbound-envelope.ts.

Inbound message envelope building: route resolution, session timestamp lookup,
envelope formatting with configurable resolvers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class RouteLike:
    agent_id: str = ""
    session_key: str = ""


@dataclass
class RoutePeerLike:
    kind: str = ""
    id: str | int = ""


@dataclass
class InboundEnvelopeFormatParams:
    channel: str = ""
    from_: str = ""
    timestamp: int | None = None
    previous_timestamp: int | None = None
    envelope: Any = None
    body: str = ""


@dataclass
class EnvelopeBuildResult:
    store_path: str = ""
    body: str = ""


def create_inbound_envelope_builder(
    cfg: Any,
    route: RouteLike,
    resolve_store_path: Callable[[str | None, dict[str, str]], str],
    read_session_updated_at: Callable[[dict[str, str]], int | None],
    resolve_envelope_format_options: Callable[[Any], Any],
    format_agent_envelope: Callable[[InboundEnvelopeFormatParams], str],
    session_store: str | None = None,
) -> Callable[..., EnvelopeBuildResult]:
    store_path = resolve_store_path(session_store, {"agent_id": route.agent_id})
    envelope_options = resolve_envelope_format_options(cfg)

    def build(channel: str, from_: str, body: str, timestamp: int | None = None) -> EnvelopeBuildResult:
        previous_timestamp = read_session_updated_at({
            "store_path": store_path,
            "session_key": route.session_key,
        })
        formatted_body = format_agent_envelope(InboundEnvelopeFormatParams(
            channel=channel, from_=from_, timestamp=timestamp,
            previous_timestamp=previous_timestamp,
            envelope=envelope_options, body=body,
        ))
        return EnvelopeBuildResult(store_path=store_path, body=formatted_body)
    return build


def resolve_inbound_route_envelope_builder(
    cfg: Any,
    channel: str,
    account_id: str,
    peer: RoutePeerLike,
    resolve_agent_route: Callable[..., RouteLike],
    resolve_store_path: Callable[[str | None, dict[str, str]], str],
    read_session_updated_at: Callable[[dict[str, str]], int | None],
    resolve_envelope_format_options: Callable[[Any], Any],
    format_agent_envelope: Callable[[InboundEnvelopeFormatParams], str],
    session_store: str | None = None,
) -> dict[str, Any]:
    route = resolve_agent_route(cfg=cfg, channel=channel, account_id=account_id, peer=peer)
    build_envelope = create_inbound_envelope_builder(
        cfg=cfg, route=route,
        resolve_store_path=resolve_store_path,
        read_session_updated_at=read_session_updated_at,
        resolve_envelope_format_options=resolve_envelope_format_options,
        format_agent_envelope=format_agent_envelope,
        session_store=session_store,
    )
    return {"route": route, "build_envelope": build_envelope}


def resolve_inbound_route_envelope_builder_with_runtime(
    cfg: Any, channel: str, account_id: str, peer: RoutePeerLike,
    runtime: dict[str, Any], session_store: str | None = None,
) -> dict[str, Any]:
    routing = runtime.get("routing", {})
    session = runtime.get("session", {})
    reply = runtime.get("reply", {})
    return resolve_inbound_route_envelope_builder(
        cfg=cfg, channel=channel, account_id=account_id, peer=peer,
        resolve_agent_route=routing.get("resolve_agent_route", lambda **_: RouteLike()),
        resolve_store_path=session.get("resolve_store_path", lambda *_: ""),
        read_session_updated_at=session.get("read_session_updated_at", lambda _: None),
        resolve_envelope_format_options=reply.get("resolve_envelope_format_options", lambda _: None),
        format_agent_envelope=reply.get("format_agent_envelope", lambda p: p.body),
        session_store=session_store,
    )

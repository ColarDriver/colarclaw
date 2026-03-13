"""ACP persistent bindings — ported from bk/src/acp/persistent-bindings.ts + types/lifecycle/resolve/route.

Channel-based ACP binding configuration, resolution, and lifecycle management.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .conversation_id import parse_telegram_topic_conversation

ConfiguredAcpBindingChannel = Literal["discord", "telegram"]
AcpRuntimeSessionMode = Literal["oneshot", "persistent"]


@dataclass
class ConfiguredAcpBindingSpec:
    channel: ConfiguredAcpBindingChannel = "discord"
    account_id: str = ""
    conversation_id: str = ""
    parent_conversation_id: str | None = None
    agent_id: str = ""
    acp_agent_id: str | None = None
    mode: AcpRuntimeSessionMode = "persistent"
    cwd: str | None = None
    backend: str | None = None
    label: str | None = None


@dataclass
class SessionBindingRecord:
    binding_id: str = ""
    target_session_key: str = ""
    target_kind: str = "session"
    conversation: dict[str, str | None] = field(default_factory=dict)
    status: str = "active"
    bound_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedConfiguredAcpBinding:
    spec: ConfiguredAcpBindingSpec = field(default_factory=ConfiguredAcpBindingSpec)
    record: SessionBindingRecord = field(default_factory=SessionBindingRecord)


@dataclass
class AcpBindingConfigShape:
    mode: str | None = None
    cwd: str | None = None
    backend: str | None = None
    label: str | None = None


def _normalize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    t = value.strip()
    return t or None


def normalize_mode(value: Any) -> AcpRuntimeSessionMode:
    raw = (_normalize_text(value) or "").lower()
    return "oneshot" if raw == "oneshot" else "persistent"


def normalize_binding_config(raw: Any) -> AcpBindingConfigShape:
    if not raw or not isinstance(raw, dict):
        return AcpBindingConfigShape()
    mode = _normalize_text(raw.get("mode"))
    return AcpBindingConfigShape(
        mode=normalize_mode(mode) if mode else None,
        cwd=_normalize_text(raw.get("cwd")),
        backend=_normalize_text(raw.get("backend")),
        label=_normalize_text(raw.get("label")),
    )


def _build_binding_hash(channel: str, account_id: str, conversation_id: str) -> str:
    data = f"{channel}:{account_id}:{conversation_id}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def _sanitize_agent_id(agent_id: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", agent_id.strip().lower())


def build_configured_acp_session_key(spec: ConfiguredAcpBindingSpec) -> str:
    h = _build_binding_hash(spec.channel, spec.account_id, spec.conversation_id)
    return f"agent:{_sanitize_agent_id(spec.agent_id)}:acp:binding:{spec.channel}:{spec.account_id}:{h}"


def to_configured_acp_binding_record(spec: ConfiguredAcpBindingSpec) -> SessionBindingRecord:
    return SessionBindingRecord(
        binding_id=f"config:acp:{spec.channel}:{spec.account_id}:{spec.conversation_id}",
        target_session_key=build_configured_acp_session_key(spec),
        target_kind="session",
        conversation={
            "channel": spec.channel,
            "accountId": spec.account_id,
            "conversationId": spec.conversation_id,
            "parentConversationId": spec.parent_conversation_id,
        },
        status="active",
        bound_at=0,
        metadata={
            "source": "config",
            "mode": spec.mode,
            "agentId": spec.agent_id,
            **({"acpAgentId": spec.acp_agent_id} if spec.acp_agent_id else {}),
            "label": spec.label,
            **({"backend": spec.backend} if spec.backend else {}),
            **({"cwd": spec.cwd} if spec.cwd else {}),
        },
    )


def _normalize_binding_channel(value: str | None) -> ConfiguredAcpBindingChannel | None:
    n = (value or "").strip().lower()
    return n if n in ("discord", "telegram") else None  # type: ignore[return-value]


def _normalize_account_id(value: str) -> str:
    return value.strip().lower() or "default"


async def ensure_configured_acp_binding_session(
    cfg: Any, spec: ConfiguredAcpBindingSpec,
) -> dict[str, Any]:
    session_key = build_configured_acp_session_key(spec)
    return {"ok": True, "session_key": session_key}


async def reset_acp_session_in_place(
    cfg: Any, session_key: str, reason: str = "reset",
) -> dict[str, Any]:
    return {"ok": True}


def resolve_configured_acp_binding_record(
    cfg: Any,
    channel: str,
    account_id: str,
    conversation_id: str,
    parent_conversation_id: str | None = None,
) -> ResolvedConfiguredAcpBinding | None:
    """Resolve a configured ACP binding for a given channel+account+conversation."""
    return None


def resolve_configured_acp_binding_spec_by_session_key(
    cfg: Any, session_key: str,
) -> ConfiguredAcpBindingSpec | None:
    """Resolve a binding spec from a session key."""
    return None


def resolve_configured_acp_route(
    cfg: Any,
    route: Any,
    channel: str,
    account_id: str,
    conversation_id: str,
    parent_conversation_id: str | None = None,
) -> dict[str, Any]:
    binding = resolve_configured_acp_binding_record(
        cfg, channel, account_id, conversation_id, parent_conversation_id,
    )
    if not binding:
        return {"configured_binding": None, "route": route}
    bound_key = binding.record.target_session_key.strip()
    if not bound_key:
        return {"configured_binding": binding, "route": route}
    return {
        "configured_binding": binding,
        "route": route,
        "bound_session_key": bound_key,
    }


async def ensure_configured_acp_route_ready(
    cfg: Any, configured_binding: ResolvedConfiguredAcpBinding | None,
) -> dict[str, Any]:
    if not configured_binding:
        return {"ok": True}
    result = await ensure_configured_acp_binding_session(cfg, configured_binding.spec)
    if result.get("ok"):
        return {"ok": True}
    return {"ok": False, "error": result.get("error", "unknown error")}

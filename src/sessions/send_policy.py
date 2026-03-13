"""Send policy — ported from bk/src/sessions/send-policy.ts.

Rule-based send policy evaluation for sessions.
"""
from __future__ import annotations

from typing import Any, Literal

from .session_key_utils import derive_session_chat_type

SendPolicyDecision = Literal["allow", "deny"]


def normalize_send_policy(raw: str | None) -> SendPolicyDecision | None:
    value = (raw or "").strip().lower()
    if value == "allow":
        return "allow"
    if value == "deny":
        return "deny"
    return None


def _normalize_match_value(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    return value or None


def _strip_agent_key_prefix(key: str | None) -> str | None:
    if not key:
        return None
    parts = [p for p in key.split(":") if p]
    if len(parts) >= 3 and parts[0] == "agent":
        return ":".join(parts[2:])
    return key


def _derive_channel_from_key(key: str | None) -> str | None:
    normalized = _strip_agent_key_prefix(key)
    if not normalized:
        return None
    parts = [p for p in normalized.split(":") if p]
    if len(parts) >= 3 and parts[1] in ("group", "channel"):
        return _normalize_match_value(parts[0])
    return None


def resolve_send_policy(
    cfg: dict[str, Any],
    entry: dict[str, Any] | None = None,
    session_key: str | None = None,
    channel: str | None = None,
    chat_type: str | None = None,
) -> SendPolicyDecision:
    """Resolve send policy for a session.

    Checks per-entry override, then evaluates rules, then falls back to default.
    """
    # Per-entry override
    if entry:
        override = normalize_send_policy(entry.get("sendPolicy"))
        if override:
            return override

    # Check policy rules
    session_cfg = cfg.get("session", {})
    policy = session_cfg.get("sendPolicy") if isinstance(session_cfg, dict) else None
    if not policy or not isinstance(policy, dict):
        return "allow"

    resolved_channel = (
        _normalize_match_value(channel)
        or _normalize_match_value(entry.get("channel") if entry else None)
        or _normalize_match_value(entry.get("lastChannel") if entry else None)
        or _derive_channel_from_key(session_key)
    )
    resolved_chat_type = chat_type or (entry.get("chatType") if entry else None)
    if not resolved_chat_type:
        resolved_chat_type = derive_session_chat_type(session_key)
    resolved_chat_type = (resolved_chat_type or "").strip().lower() or None

    raw_key = (session_key or "").lower()
    stripped_key = (_strip_agent_key_prefix(session_key) or "").lower()

    allowed_match = False
    for rule in policy.get("rules", []):
        if not rule:
            continue
        action = normalize_send_policy(rule.get("action")) or "allow"
        match = rule.get("match", {})
        match_channel = _normalize_match_value(match.get("channel"))
        match_chat_type = _normalize_match_value(match.get("chatType"))
        match_prefix = _normalize_match_value(match.get("keyPrefix"))
        match_raw_prefix = _normalize_match_value(match.get("rawKeyPrefix"))

        if match_channel and match_channel != resolved_channel:
            continue
        if match_chat_type and match_chat_type != resolved_chat_type:
            continue
        if match_raw_prefix and not raw_key.startswith(match_raw_prefix):
            continue
        if match_prefix and not raw_key.startswith(match_prefix) and not stripped_key.startswith(match_prefix):
            continue

        if action == "deny":
            return "deny"
        allowed_match = True

    if allowed_match:
        return "allow"

    fallback = normalize_send_policy(policy.get("default"))
    return fallback or "allow"

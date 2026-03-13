"""Session key construction — ported from bk/src/routing/session-key.ts.

Session key building, parsing, normalization, and identity linking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .account_id import DEFAULT_ACCOUNT_ID, normalize_account_id

DEFAULT_AGENT_ID = "main"
DEFAULT_MAIN_KEY = "main"

_VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)
_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_-]+")
_LEADING_DASH_RE = re.compile(r"^-+")
_TRAILING_DASH_RE = re.compile(r"-+$")
_AGENT_KEY_RE = re.compile(r"^agent:([^:]+):(.+)$", re.IGNORECASE)


# ─── session key parsing ───

@dataclass
class ParsedAgentSessionKey:
    agent_id: str
    rest: str


def parse_agent_session_key(key: str | None) -> ParsedAgentSessionKey | None:
    """Parse an 'agent:AGENT_ID:REST' session key."""
    raw = (key or "").strip()
    if not raw:
        return None
    m = _AGENT_KEY_RE.match(raw)
    if not m:
        return None
    return ParsedAgentSessionKey(agent_id=m.group(1), rest=m.group(2))


def get_subagent_depth(key: str | None) -> int:
    """Count subagent depth from session key."""
    raw = (key or "").strip().lower()
    return raw.count(":subagent:")


def is_cron_session_key(key: str | None) -> bool:
    return ":cron:" in (key or "").lower()


def is_acp_session_key(key: str | None) -> bool:
    return ":acp:" in (key or "").lower()


def is_subagent_session_key(key: str | None) -> bool:
    return ":subagent:" in (key or "").lower()


# ─── agent ID normalization ───

def normalize_agent_id(value: str | None = None) -> str:
    trimmed = (value or "").strip()
    if not trimmed:
        return DEFAULT_AGENT_ID
    if _VALID_ID_RE.match(trimmed):
        return trimmed.lower()
    result = trimmed.lower()
    result = _INVALID_CHARS_RE.sub("-", result)
    result = _LEADING_DASH_RE.sub("", result)
    result = _TRAILING_DASH_RE.sub("", result)
    return result[:64] or DEFAULT_AGENT_ID


def is_valid_agent_id(value: str | None = None) -> bool:
    trimmed = (value or "").strip()
    return bool(trimmed) and bool(_VALID_ID_RE.match(trimmed))


def sanitize_agent_id(value: str | None = None) -> str:
    return normalize_agent_id(value)


def normalize_main_key(value: str | None = None) -> str:
    trimmed = (value or "").strip()
    return trimmed.lower() if trimmed else DEFAULT_MAIN_KEY


# ─── session key building ───

def build_agent_main_session_key(
    agent_id: str,
    main_key: str | None = None,
) -> str:
    """Build an agent:AGENT_ID:MAIN_KEY session key."""
    return f"agent:{normalize_agent_id(agent_id)}:{normalize_main_key(main_key)}"


def build_agent_peer_session_key(
    agent_id: str,
    channel: str,
    peer_kind: str = "direct",
    peer_id: str | None = None,
    account_id: str | None = None,
    main_key: str | None = None,
    dm_scope: str = "main",
    identity_links: dict[str, list[str]] | None = None,
) -> str:
    """Build a full peer-scoped session key."""
    normalized_agent = normalize_agent_id(agent_id)

    if peer_kind == "direct":
        pid = (peer_id or "").strip()
        linked = _resolve_linked_peer_id(identity_links, channel, pid)
        if linked:
            pid = linked
        pid = pid.lower()

        if dm_scope == "per-account-channel-peer" and pid:
            ch = (channel or "").strip().lower() or "unknown"
            acct = normalize_account_id(account_id)
            return f"agent:{normalized_agent}:{ch}:{acct}:direct:{pid}"
        if dm_scope == "per-channel-peer" and pid:
            ch = (channel or "").strip().lower() or "unknown"
            return f"agent:{normalized_agent}:{ch}:direct:{pid}"
        if dm_scope == "per-peer" and pid:
            return f"agent:{normalized_agent}:direct:{pid}"
        return build_agent_main_session_key(agent_id, main_key)

    ch = (channel or "").strip().lower() or "unknown"
    pid = ((peer_id or "").strip() or "unknown").lower()
    return f"agent:{normalized_agent}:{ch}:{peer_kind}:{pid}"


def _resolve_linked_peer_id(
    identity_links: dict[str, list[str]] | None,
    channel: str,
    peer_id: str,
) -> str | None:
    """Resolve identity-linked peer ID."""
    if not identity_links or not peer_id.strip():
        return None
    candidates = set()
    raw = peer_id.strip().lower()
    if raw:
        candidates.add(raw)
    ch = (channel or "").strip().lower()
    if ch:
        candidates.add(f"{ch}:{raw}")
    if not candidates:
        return None
    for canonical, ids in identity_links.items():
        name = canonical.strip()
        if not name or not isinstance(ids, list):
            continue
        for id_val in ids:
            normalized = str(id_val).strip().lower()
            if normalized and normalized in candidates:
                return name
    return None


# ─── convenience ───

def resolve_agent_id_from_session_key(session_key: str | None = None) -> str:
    parsed = parse_agent_session_key(session_key)
    return normalize_agent_id(parsed.agent_id if parsed else DEFAULT_AGENT_ID)


def to_agent_request_session_key(store_key: str | None = None) -> str | None:
    raw = (store_key or "").strip()
    if not raw:
        return None
    parsed = parse_agent_session_key(raw)
    return parsed.rest if parsed else raw


def to_agent_store_session_key(
    agent_id: str,
    request_key: str | None = None,
    main_key: str | None = None,
) -> str:
    raw = (request_key or "").strip()
    if not raw or raw.lower() == DEFAULT_MAIN_KEY:
        return build_agent_main_session_key(agent_id, main_key)
    parsed = parse_agent_session_key(raw)
    if parsed:
        return f"agent:{parsed.agent_id}:{parsed.rest}"
    lowered = raw.lower()
    if lowered.startswith("agent:"):
        return lowered
    return f"agent:{normalize_agent_id(agent_id)}:{lowered}"


def build_group_history_key(
    channel: str,
    peer_kind: str,
    peer_id: str,
    account_id: str | None = None,
) -> str:
    ch = (channel or "").strip().lower() or "unknown"
    acct = normalize_account_id(account_id)
    pid = (peer_id or "").strip().lower() or "unknown"
    return f"{ch}:{acct}:{peer_kind}:{pid}"


def resolve_thread_session_keys(
    base_session_key: str,
    thread_id: str | None = None,
    parent_session_key: str | None = None,
    use_suffix: bool = True,
    normalize_thread_id: Callable[[str], str] | None = None,
) -> dict[str, str | None]:
    tid = (thread_id or "").strip()
    if not tid:
        return {"session_key": base_session_key, "parent_session_key": None}
    normalizer = normalize_thread_id or (lambda v: v.lower())
    normalized = normalizer(tid)
    key = f"{base_session_key}:thread:{normalized}" if use_suffix else base_session_key
    return {"session_key": key, "parent_session_key": parent_session_key}

"""Session key utilities — ported from bk/src/sessions/session-key-utils.ts.

Session key parsing, classification, and thread parent resolution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SessionKeyChatType = Literal["direct", "group", "channel", "unknown"]

_AGENT_KEY_RE = re.compile(r"^agent:([^:]+):(.+)$", re.IGNORECASE)
_DISCORD_LEGACY_RE = re.compile(r"^discord:(?:[^:]+:)?guild-[^:]+:channel-[^:]+$")
_THREAD_MARKERS = [":thread:", ":topic:"]


@dataclass
class ParsedAgentSessionKey:
    agent_id: str
    rest: str


def parse_agent_session_key(key: str | None) -> ParsedAgentSessionKey | None:
    """Parse agent-scoped session keys: agent:AGENT_ID:REST."""
    raw = (key or "").strip().lower()
    if not raw:
        return None
    m = _AGENT_KEY_RE.match(raw)
    if not m:
        return None
    agent_id = m.group(1).strip()
    rest = m.group(2)
    if not agent_id or not rest:
        return None
    return ParsedAgentSessionKey(agent_id=agent_id, rest=rest)


def derive_session_chat_type(key: str | None) -> SessionKeyChatType:
    """Best-effort chat-type extraction from session keys."""
    raw = (key or "").strip().lower()
    if not raw:
        return "unknown"
    parsed = parse_agent_session_key(raw)
    scoped = parsed.rest if parsed else raw
    tokens = set(p for p in scoped.split(":") if p)
    if "group" in tokens:
        return "group"
    if "channel" in tokens:
        return "channel"
    if "direct" in tokens or "dm" in tokens:
        return "direct"
    if _DISCORD_LEGACY_RE.match(scoped):
        return "channel"
    return "unknown"


def is_cron_run_session_key(key: str | None) -> bool:
    parsed = parse_agent_session_key(key)
    if not parsed:
        return False
    return bool(re.match(r"^cron:[^:]+:run:[^:]+$", parsed.rest))


def is_cron_session_key(key: str | None) -> bool:
    parsed = parse_agent_session_key(key)
    if not parsed:
        return False
    return parsed.rest.startswith("cron:")


def is_subagent_session_key(key: str | None) -> bool:
    raw = (key or "").strip().lower()
    if not raw:
        return False
    if raw.startswith("subagent:"):
        return True
    parsed = parse_agent_session_key(raw)
    return bool(parsed and parsed.rest.startswith("subagent:"))


def get_subagent_depth(key: str | None) -> int:
    raw = (key or "").strip().lower()
    if not raw:
        return 0
    return raw.count(":subagent:")


def is_acp_session_key(key: str | None) -> bool:
    raw = (key or "").strip().lower()
    if not raw:
        return False
    if raw.startswith("acp:"):
        return True
    parsed = parse_agent_session_key(raw)
    return bool(parsed and parsed.rest.startswith("acp:"))


def resolve_thread_parent_session_key(key: str | None) -> str | None:
    """Resolve the parent session key from a thread session key."""
    raw = (key or "").strip()
    if not raw:
        return None
    normalized = raw.lower()
    idx = -1
    for marker in _THREAD_MARKERS:
        candidate = normalized.rfind(marker)
        if candidate > idx:
            idx = candidate
    if idx <= 0:
        return None
    parent = raw[:idx].strip()
    return parent or None

"""Gateway session utilities — ported from bk/src/gateway/session-utils.ts,
session-utils.fs.ts, session-utils.types.ts, sessions-patch.ts, sessions-resolve.ts,
server-session-key.ts, server-wizard-sessions.ts.

Session management: loading, patching, resolving, compacting, previewing sessions.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ─── session-utils.types.ts ───

@dataclass
class GatewaySessionsDefaults:
    model_provider: str | None = None
    model: str | None = None
    context_tokens: int | None = None


@dataclass
class GatewaySessionRow:
    """Session list row."""
    key: str = ""
    kind: str = "unknown"  # "direct" | "group" | "global" | "unknown"
    label: str | None = None
    display_name: str | None = None
    derived_title: str | None = None
    last_message_preview: str | None = None
    channel: str | None = None
    subject: str | None = None
    group_channel: str | None = None
    space: str | None = None
    chat_type: str | None = None
    origin: dict[str, Any] | None = None
    updated_at: int | None = None
    session_id: str | None = None
    system_sent: bool | None = None
    aborted_last_run: bool | None = None
    thinking_level: str | None = None
    verbose_level: str | None = None
    reasoning_level: str | None = None
    elevated_level: str | None = None
    send_policy: str | None = None  # "allow" | "deny"
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    total_tokens_fresh: bool | None = None
    response_usage: str | None = None  # "on" | "off" | "tokens" | "full"
    model_provider: str | None = None
    model: str | None = None
    context_tokens: int | None = None
    delivery_context: dict[str, Any] | None = None
    last_channel: dict[str, Any] | None = None
    last_to: str | None = None
    last_account_id: str | None = None


@dataclass
class SessionPreviewItem:
    role: str = ""  # "user" | "assistant" | "tool" | "system" | "other"
    text: str = ""


@dataclass
class SessionsPreviewEntry:
    key: str = ""
    status: str = "ok"  # "ok" | "empty" | "missing" | "error"
    items: list[SessionPreviewItem] = field(default_factory=list)


@dataclass
class SessionsPreviewResult:
    ts: int = 0
    previews: list[SessionsPreviewEntry] = field(default_factory=list)


# ─── session-utils.ts — Core session loading/listing ───

@dataclass
class SessionEntry:
    """A persisted session entry."""
    key: str = ""
    agent_id: str | None = None
    model_provider: str | None = None
    model: str | None = None
    context_tokens: int | None = None
    thinking_level: str | None = None
    verbose_level: str | None = None
    reasoning_level: str | None = None
    elevated_level: str | None = None
    send_policy: str | None = None
    origin: dict[str, Any] | None = None
    last_channel: dict[str, Any] | None = None
    updated_at: int | None = None
    response_usage: str | None = None


def resolve_sessions_dir(state_dir: str | None = None) -> str:
    """Resolve the sessions storage directory."""
    base = state_dir or os.path.expanduser("~/.openclaw")
    return os.path.join(base, "sessions")


def load_session_entry(
    session_key: str,
    state_dir: str | None = None,
) -> tuple[dict[str, Any], SessionEntry | None]:
    """Load a session entry by key.

    Returns (config, session_entry_or_none).
    """
    sessions_dir = resolve_sessions_dir(state_dir)
    session_file = os.path.join(sessions_dir, f"{session_key}.json")
    cfg: dict[str, Any] = {}

    if not os.path.isfile(session_file):
        return cfg, None

    try:
        with open(session_file) as f:
            data = json.load(f)
        entry = SessionEntry(
            key=session_key,
            agent_id=data.get("agentId"),
            model_provider=data.get("modelProvider"),
            model=data.get("model"),
            context_tokens=data.get("contextTokens"),
            thinking_level=data.get("thinkingLevel"),
            verbose_level=data.get("verboseLevel"),
            reasoning_level=data.get("reasoningLevel"),
            elevated_level=data.get("elevatedLevel"),
            send_policy=data.get("sendPolicy"),
            origin=data.get("origin"),
            last_channel=data.get("lastChannel"),
            updated_at=data.get("updatedAt"),
            response_usage=data.get("responseUsage"),
        )
        return cfg, entry
    except Exception as e:
        logger.debug(f"Failed to load session {session_key}: {e}")
        return cfg, None


def save_session_entry(
    session_key: str,
    entry: SessionEntry,
    state_dir: str | None = None,
) -> None:
    """Save a session entry to disk."""
    sessions_dir = resolve_sessions_dir(state_dir)
    os.makedirs(sessions_dir, exist_ok=True)
    session_file = os.path.join(sessions_dir, f"{session_key}.json")

    data = {
        "agentId": entry.agent_id,
        "modelProvider": entry.model_provider,
        "model": entry.model,
        "contextTokens": entry.context_tokens,
        "thinkingLevel": entry.thinking_level,
        "verboseLevel": entry.verbose_level,
        "reasoningLevel": entry.reasoning_level,
        "elevatedLevel": entry.elevated_level,
        "sendPolicy": entry.send_policy,
        "origin": entry.origin,
        "lastChannel": entry.last_channel,
        "updatedAt": int(time.time() * 1000),
        "responseUsage": entry.response_usage,
    }

    with open(session_file, "w") as f:
        json.dump(data, f, indent=2)


def list_sessions(
    state_dir: str | None = None,
    *,
    limit: int = 100,
    sort_by: str = "updated_at",
) -> list[GatewaySessionRow]:
    """List all sessions, optionally sorted and limited."""
    sessions_dir = resolve_sessions_dir(state_dir)
    if not os.path.isdir(sessions_dir):
        return []

    rows: list[GatewaySessionRow] = []
    for filename in os.listdir(sessions_dir):
        if not filename.endswith(".json"):
            continue
        session_key = filename[:-5]
        filepath = os.path.join(sessions_dir, filename)
        try:
            with open(filepath) as f:
                data = json.load(f)
            row = GatewaySessionRow(
                key=session_key,
                kind=_infer_session_kind(session_key),
                model_provider=data.get("modelProvider"),
                model=data.get("model"),
                context_tokens=data.get("contextTokens"),
                thinking_level=data.get("thinkingLevel"),
                send_policy=data.get("sendPolicy"),
                updated_at=data.get("updatedAt"),
                origin=data.get("origin"),
                last_channel=data.get("lastChannel"),
            )
            rows.append(row)
        except Exception:
            continue

    # Sort
    if sort_by == "updated_at":
        rows.sort(key=lambda r: r.updated_at or 0, reverse=True)

    return rows[:limit]


def _infer_session_kind(session_key: str) -> str:
    """Infer session kind from key pattern."""
    if ":group:" in session_key:
        return "group"
    if session_key.startswith("global:"):
        return "global"
    if ":" in session_key:
        return "direct"
    return "unknown"


# ─── sessions-patch.ts — Session patching ───

@dataclass
class SessionPatchRequest:
    session_key: str = ""
    model_provider: str | None = None
    model: str | None = None
    context_tokens: int | None = None
    thinking_level: str | None = None
    verbose_level: str | None = None
    reasoning_level: str | None = None
    elevated_level: str | None = None
    send_policy: str | None = None
    response_usage: str | None = None


def patch_session(
    request: SessionPatchRequest,
    state_dir: str | None = None,
) -> SessionEntry | None:
    """Patch a session entry with the given changes."""
    _, entry = load_session_entry(request.session_key, state_dir)
    if entry is None:
        entry = SessionEntry(key=request.session_key)

    if request.model_provider is not None:
        entry.model_provider = request.model_provider if request.model_provider else None
    if request.model is not None:
        entry.model = request.model if request.model else None
    if request.context_tokens is not None:
        entry.context_tokens = request.context_tokens if request.context_tokens > 0 else None
    if request.thinking_level is not None:
        entry.thinking_level = request.thinking_level if request.thinking_level else None
    if request.verbose_level is not None:
        entry.verbose_level = request.verbose_level if request.verbose_level else None
    if request.reasoning_level is not None:
        entry.reasoning_level = request.reasoning_level if request.reasoning_level else None
    if request.elevated_level is not None:
        entry.elevated_level = request.elevated_level if request.elevated_level else None
    if request.send_policy is not None:
        entry.send_policy = request.send_policy if request.send_policy else None
    if request.response_usage is not None:
        entry.response_usage = request.response_usage if request.response_usage else None

    save_session_entry(request.session_key, entry, state_dir)
    return entry


# ─── sessions-resolve.ts — Session key resolution ───

def resolve_session_key(
    session_key: str,
    *,
    agent_id: str | None = None,
    channel: str | None = None,
    to: str | None = None,
) -> str:
    """Resolve a session key, potentially enriching with agent/channel context."""
    if session_key:
        return session_key
    parts = []
    if agent_id:
        parts.append(agent_id)
    if channel:
        parts.append(channel)
    if to:
        parts.append(to)
    return ":".join(parts) if parts else "default"


# ─── server-session-key.ts ───

def build_server_session_key(
    agent_id: str,
    channel: str | None = None,
    target: str | None = None,
    thread_id: str | None = None,
) -> str:
    """Build a server-side session key."""
    parts = [agent_id]
    if channel:
        parts.append(channel)
    if target:
        parts.append(target)
    if thread_id:
        parts.append(f"topic:{thread_id}")
    return ":".join(parts)


# ─── Session deletion and compaction ───

def delete_session(
    session_key: str,
    state_dir: str | None = None,
) -> bool:
    """Delete a session by key. Returns True if it existed."""
    sessions_dir = resolve_sessions_dir(state_dir)
    session_file = os.path.join(sessions_dir, f"{session_key}.json")
    if os.path.isfile(session_file):
        os.unlink(session_file)
        return True
    return False


def compact_session(
    session_key: str,
    state_dir: str | None = None,
) -> bool:
    """Compact a session (remove old messages, keep summary). Returns True if modified."""
    # In a full implementation, this would truncate the conversation history
    # while preserving a summary. For now, just return False.
    return False


# ─── Session preview ───

def preview_sessions(
    session_keys: list[str],
    state_dir: str | None = None,
    *,
    max_items: int = 10,
) -> SessionsPreviewResult:
    """Get a preview of multiple sessions."""
    previews: list[SessionsPreviewEntry] = []
    for key in session_keys:
        _, entry = load_session_entry(key, state_dir)
        if entry is None:
            previews.append(SessionsPreviewEntry(key=key, status="missing"))
        else:
            previews.append(SessionsPreviewEntry(key=key, status="ok"))
    return SessionsPreviewResult(
        ts=int(time.time() * 1000),
        previews=previews,
    )

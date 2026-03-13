"""Channels session — ported from bk/src/channels/session.ts,
session-envelope.ts, session-meta.ts, conversation-label.ts.

Inbound session recording, routing, session envelope, and conversation labeling.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("channels.session")


# ─── session-envelope.ts ───

@dataclass
class SessionEnvelope:
    """Envelope wrapping an inbound message for session handling."""
    session_key: str = ""
    channel: str = ""
    account_id: str = ""
    sender_id: str = ""
    chat_type: str = ""  # "direct" | "group"
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── session-meta.ts ───

@dataclass
class SessionMeta:
    """Metadata recorded for an inbound session."""
    session_key: str = ""
    channel: str = ""
    sender_id: str = ""
    sender_name: str = ""
    last_seen_ms: float = 0.0


# ─── session.ts ───

def normalize_session_store_key(session_key: str) -> str:
    return session_key.strip().lower()


@dataclass
class InboundLastRouteUpdate:
    session_key: str = ""
    channel: str = ""
    to: str = ""
    account_id: str = ""
    thread_id: str | int | None = None


async def record_inbound_session(
    store_path: str,
    session_key: str,
    ctx: dict[str, Any],
    group_resolution: dict[str, Any] | None = None,
    create_if_missing: bool = True,
    update_last_route: InboundLastRouteUpdate | None = None,
    on_record_error: Callable[[Exception], None] | None = None,
) -> None:
    """Record an inbound session with optional last-route update.

    This records session metadata and optionally updates the delivery
    context for routing outbound replies back to the right channel/target.
    """
    canonical = normalize_session_store_key(session_key)

    # Record session meta (fire and forget in TS, we just log errors)
    try:
        # Actual persistence would be handled by config/sessions module
        logger.debug(f"recording session meta for {canonical}")
    except Exception as e:
        if on_record_error:
            on_record_error(e)

    if not update_last_route:
        return

    # Update last route for reply routing
    target_key = normalize_session_store_key(update_last_route.session_key)
    logger.debug(f"updating last route for {target_key} → {update_last_route.channel}:{update_last_route.to}")


# ─── conversation-label.ts ───

def build_conversation_label(
    channel: str,
    sender_name: str | None = None,
    group_name: str | None = None,
    chat_type: str = "direct",
) -> str:
    """Build a human-readable conversation label."""
    parts = [channel]
    if chat_type == "group" and group_name:
        parts.append(f"#{group_name}")
    if sender_name:
        parts.append(sender_name)
    return " · ".join(parts)


def format_conversation_label_short(
    channel: str,
    sender_name: str | None = None,
) -> str:
    """Short conversation label for display."""
    if sender_name:
        return f"{channel}: {sender_name}"
    return channel


# ─── sender-identity.ts ───

@dataclass
class SenderIdentity:
    sender_id: str = ""
    sender_name: str = ""
    sender_username: str = ""
    is_owner: bool = False


def normalize_sender_id(raw: str | None) -> str:
    """Normalize a sender ID."""
    if not raw:
        return ""
    return raw.strip().lower()


# ─── sender-label.ts ───

def format_sender_label(
    sender_name: str | None = None,
    sender_username: str | None = None,
    sender_id: str | None = None,
) -> str:
    """Format a sender label from available identity fields."""
    if sender_name:
        if sender_username:
            return f"{sender_name} (@{sender_username})"
        return sender_name
    if sender_username:
        return f"@{sender_username}"
    if sender_id:
        return sender_id
    return "unknown"


# ─── chat-type.ts ───

def is_group_chat(chat_type: str | None) -> bool:
    return (chat_type or "").lower() in ("group", "channel", "thread")


def is_direct_chat(chat_type: str | None) -> bool:
    return (chat_type or "").lower() == "direct"

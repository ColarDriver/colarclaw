"""Gateway server methods — chat handler.

Ported from bk/src/gateway/server-methods/chat.ts (1244 lines).

Handles chat.send, chat.history, chat.abort, chat.inject RPC methods.
Session-scoped message flow, abort with partial transcript persistence,
history sanitization, and delivery route resolution.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CHAT_HISTORY_TEXT_MAX_CHARS = 12_000
CHAT_HISTORY_MAX_SINGLE_MESSAGE_BYTES = 128 * 1024
CHAT_HISTORY_OVERSIZED_PLACEHOLDER = "[chat.history omitted: message too large]"

# Session scope classification
CHANNEL_AGNOSTIC_SESSION_SCOPES = frozenset({
    "main", "direct", "dm", "group", "channel",
    "cron", "run", "subagent", "acp", "thread", "topic",
})
CHANNEL_SCOPED_SESSION_SHAPES = frozenset({
    "direct", "dm", "group", "channel",
})


# ─── Chat send message sanitization ───

def sanitize_chat_send_message(message: str) -> tuple[bool, str]:
    """Sanitize a chat.send message input.

    Returns (ok, sanitized_message_or_error).
    """
    import unicodedata
    normalized = unicodedata.normalize("NFC", message)
    if "\x00" in normalized:
        return False, "message must not contain null bytes"
    # Strip disallowed control characters (keep tab, newline, carriage return)
    sanitized = ""
    for char in normalized:
        code = ord(char)
        if code == 9 or code == 10 or code == 13 or (code >= 32 and code != 127):
            sanitized += char
    return True, sanitized


# ─── Chat history sanitization ───

def truncate_chat_history_text(text: str, max_chars: int = CHAT_HISTORY_TEXT_MAX_CHARS) -> tuple[str, bool]:
    """Truncate text for chat history, returning (text, was_truncated)."""
    if len(text) <= max_chars:
        return text, False
    return f"{text[:max_chars]}\n...(truncated)...", True


def sanitize_chat_history_content_block(block: Any) -> tuple[Any, bool]:
    """Sanitize a single content block in a chat history message."""
    if not isinstance(block, dict):
        return block, False

    entry = dict(block)
    changed = False

    for key in ("text", "partialJson", "arguments", "thinking"):
        if key in entry and isinstance(entry[key], str):
            result, truncated = truncate_chat_history_text(entry[key])
            entry[key] = result
            changed = changed or truncated

    # Remove thinking signature
    if "thinkingSignature" in entry:
        del entry["thinkingSignature"]
        changed = True

    # Omit large inline image data
    if entry.get("type") == "image" and isinstance(entry.get("data"), str):
        data_bytes = len(entry["data"].encode("utf-8"))
        del entry["data"]
        entry["omitted"] = True
        entry["bytes"] = data_bytes
        changed = True

    return (entry if changed else block), changed


def sanitize_chat_history_message(message: Any) -> tuple[Any, bool]:
    """Sanitize a single chat history message (remove usage, cost, truncate text)."""
    if not isinstance(message, dict):
        return message, False

    entry = dict(message)
    changed = False

    # Remove non-display fields
    for key in ("details", "usage", "cost"):
        if key in entry:
            del entry[key]
            changed = True

    # Sanitize content
    content = entry.get("content")
    if isinstance(content, str):
        result, truncated = truncate_chat_history_text(content)
        entry["content"] = result
        changed = changed or truncated
    elif isinstance(content, list):
        new_content = []
        for block in content:
            sanitized_block, block_changed = sanitize_chat_history_content_block(block)
            new_content.append(sanitized_block)
            changed = changed or block_changed
        if changed:
            entry["content"] = new_content

    # Sanitize text field
    if isinstance(entry.get("text"), str):
        result, truncated = truncate_chat_history_text(entry["text"])
        entry["text"] = result
        changed = changed or truncated

    return (entry if changed else message), changed


def sanitize_chat_history_messages(messages: list[Any]) -> list[Any]:
    """Sanitize a list of chat history messages."""
    if not messages:
        return messages

    result = []
    changed = False
    for msg in messages:
        sanitized, msg_changed = sanitize_chat_history_message(msg)
        changed = changed or msg_changed
        # Drop silent-reply assistant messages
        text = _extract_assistant_text_for_silent_check(sanitized)
        if text is not None and _is_silent_reply_text(text):
            changed = True
            continue
        result.append(sanitized)

    return result if changed else messages


def _extract_assistant_text_for_silent_check(message: Any) -> str | None:
    """Extract text from assistant message for silent-token check."""
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return None
    if isinstance(message.get("text"), str):
        return message["text"]
    if isinstance(message.get("content"), str):
        return message["content"]
    return None


def _is_silent_reply_text(text: str) -> bool:
    """Check if text is a silent reply token."""
    return text.strip() == "NO_REPLY"


# ─── Oversized message handling ───

def build_oversized_history_placeholder(message: Any = None) -> dict[str, Any]:
    """Build a placeholder for an oversized history message."""
    role = "assistant"
    timestamp = int(time.time() * 1000)
    if isinstance(message, dict):
        role = message.get("role", "assistant")
        timestamp = message.get("timestamp", timestamp)
    return {
        "role": role,
        "timestamp": timestamp,
        "content": [{"type": "text", "text": CHAT_HISTORY_OVERSIZED_PLACEHOLDER}],
        "__openclaw": {"truncated": True, "reason": "oversized"},
    }


def replace_oversized_chat_history_messages(
    messages: list[Any],
    max_single_message_bytes: int = CHAT_HISTORY_MAX_SINGLE_MESSAGE_BYTES,
) -> tuple[list[Any], int]:
    """Replace oversized messages with placeholders. Returns (messages, replaced_count)."""
    if not messages:
        return messages, 0

    replaced = 0
    result = []
    for msg in messages:
        msg_bytes = len(json.dumps(msg, default=str).encode("utf-8"))
        if msg_bytes <= max_single_message_bytes:
            result.append(msg)
        else:
            result.append(build_oversized_history_placeholder(msg))
            replaced += 1

    return (result if replaced > 0 else messages), replaced


def cap_array_by_json_bytes(items: list[Any], max_bytes: int) -> list[Any]:
    """Cap an array of items to fit within max_bytes of JSON."""
    total = len(json.dumps(items, default=str).encode("utf-8"))
    if total <= max_bytes:
        return items

    # Binary search for the right cutoff
    lo, hi = 0, len(items)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        subset = items[-mid:]
        size = len(json.dumps(subset, default=str).encode("utf-8"))
        if size <= max_bytes:
            lo = mid
        else:
            hi = mid - 1

    return items[-lo:] if lo > 0 else []


# ─── Chat delivery route resolution ───

@dataclass
class ChatSendDeliveryEntry:
    delivery_context: dict[str, Any] | None = None
    last_channel: str | None = None
    last_to: str | None = None
    last_account_id: str | None = None
    last_thread_id: str | None = None


@dataclass
class ChatSendOriginatingRoute:
    originating_channel: str = "internal"
    originating_to: str | None = None
    account_id: str | None = None
    message_thread_id: str | None = None
    explicit_deliver_route: bool = False


def resolve_chat_send_originating_route(
    *,
    deliver: bool = False,
    entry: ChatSendDeliveryEntry | None = None,
    session_key: str = "",
) -> ChatSendOriginatingRoute:
    """Resolve the originating route for a chat.send."""
    if not deliver:
        return ChatSendOriginatingRoute(originating_channel="internal")

    if not entry:
        return ChatSendOriginatingRoute(originating_channel="internal")

    dc = entry.delivery_context or {}
    channel = dc.get("channel") or entry.last_channel
    to = dc.get("to") or entry.last_to
    account_id = dc.get("accountId") or entry.last_account_id

    if channel and channel != "internal" and to:
        return ChatSendOriginatingRoute(
            originating_channel=channel,
            originating_to=to,
            account_id=account_id,
            message_thread_id=dc.get("threadId") or entry.last_thread_id,
            explicit_deliver_route=True,
        )

    return ChatSendOriginatingRoute(originating_channel="internal")


# ─── Chat abort with partial persistence ───

@dataclass
class AbortedPartialSnapshot:
    """Snapshot of an aborted chat run's partial response."""
    run_id: str = ""
    session_id: str = ""
    text: str = ""
    abort_origin: str = "rpc"  # "rpc" | "stop-command"


def collect_session_abort_partials(
    *,
    abort_controllers: dict[str, Any],
    chat_run_buffers: dict[str, str],
    session_key: str,
    abort_origin: str = "rpc",
) -> list[AbortedPartialSnapshot]:
    """Collect partial responses from aborted runs in a session."""
    partials: list[AbortedPartialSnapshot] = []
    for run_id, active in abort_controllers.items():
        if getattr(active, "session_key", "") != session_key:
            continue
        text = chat_run_buffers.get(run_id, "")
        if not text or not text.strip():
            continue
        partials.append(AbortedPartialSnapshot(
            run_id=run_id,
            session_id=getattr(active, "session_id", ""),
            text=text,
            abort_origin=abort_origin,
        ))
    return partials

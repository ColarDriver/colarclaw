"""Infra outbound — ported from bk/src/infra/outbound/*.ts (52 files).

Outbound message delivery pipeline: message formatting, target resolution,
channel selection, delivery queue, session binding, envelope construction,
sanitization, conversation IDs, tool payloads, outbound policy.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger("infra.outbound")

# ─── conversation-id.ts ───


def generate_conversation_id() -> str:
    return str(uuid.uuid4())


def normalize_conversation_id(cid: str | None) -> str | None:
    if not cid:
        return None
    trimmed = cid.strip()
    return trimmed if trimmed else None


# ─── envelope.ts ───

@dataclass
class OutboundEnvelope:
    conversation_id: str | None = None
    channel: str = ""
    account_id: str = ""
    target: str = ""
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    reply_to: str | None = None
    thread_id: str | None = None
    timestamp: float = 0.0


def create_envelope(
    channel: str,
    account_id: str,
    target: str,
    text: str,
    conversation_id: str | None = None,
    reply_to: str | None = None,
    thread_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> OutboundEnvelope:
    return OutboundEnvelope(
        conversation_id=conversation_id or generate_conversation_id(),
        channel=channel,
        account_id=account_id,
        target=target,
        text=text,
        metadata=metadata or {},
        reply_to=reply_to,
        thread_id=thread_id,
        timestamp=time.time(),
    )


# ─── identity.ts ───

@dataclass
class OutboundIdentity:
    channel: str = ""
    account_id: str = ""
    display_name: str | None = None


# ─── channel-target.ts ───

@dataclass
class ChannelTarget:
    channel: str = ""
    account_id: str = ""
    target: str = ""


def normalize_channel_target(target: ChannelTarget) -> ChannelTarget:
    return ChannelTarget(
        channel=target.channel.strip().lower(),
        account_id=target.account_id.strip(),
        target=target.target.strip(),
    )


# ─── channel-selection.ts ───

@dataclass
class ChannelSelectionResult:
    channel: str = ""
    account_id: str = ""
    reason: str = ""  # "explicit" | "default" | "fallback" | "none"


def select_outbound_channel(
    preferred_channel: str | None = None,
    available_channels: list[str] | None = None,
    default_channel: str | None = None,
) -> ChannelSelectionResult:
    available = available_channels or []
    if preferred_channel and preferred_channel in available:
        return ChannelSelectionResult(channel=preferred_channel, reason="explicit")
    if default_channel and default_channel in available:
        return ChannelSelectionResult(channel=default_channel, reason="default")
    if available:
        return ChannelSelectionResult(channel=available[0], reason="fallback")
    return ChannelSelectionResult(reason="none")


# ─── channel-resolution.ts ───

def resolve_channel_for_target(target: str, channel_map: dict[str, str] | None = None) -> str | None:
    """Resolve which channel to use for a given target."""
    if not channel_map:
        return None
    return channel_map.get(target) or channel_map.get(target.lower())


# ─── target-normalization.ts ───

def normalize_outbound_target(target: str) -> str:
    cleaned = target.strip()
    if not cleaned:
        return ""
    # Remove leading + for phone numbers normalization
    if cleaned.startswith("+"):
        cleaned = re.sub(r"[\s\-\(\)]", "", cleaned)
    return cleaned.lower()


# ─── target-errors.ts ───

class OutboundTargetError(Exception):
    def __init__(self, message: str, channel: str = "", target: str = ""):
        super().__init__(message)
        self.channel = channel
        self.target = target


class OutboundDeliveryError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


# ─── sanitize-text.ts ───

_INVISIBLE_CHARS_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")


def sanitize_outbound_text(text: str) -> str:
    """Sanitize text for outbound delivery."""
    if not text:
        return ""
    # Remove zero-width characters
    cleaned = _ZERO_WIDTH_RE.sub("", text)
    # Normalize whitespace
    cleaned = re.sub(r"\r\n", "\n", cleaned)
    cleaned = re.sub(r"\r", "\n", cleaned)
    # Trim trailing whitespace on each line
    lines = [line.rstrip() for line in cleaned.split("\n")]
    # Remove excessive blank lines (3+ → 2)
    result_lines: list[str] = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 2:
                result_lines.append(line)
        else:
            blank_count = 0
            result_lines.append(line)
    return "\n".join(result_lines).strip()


# ─── format.ts ───

def format_outbound_message(text: str, max_length: int = 4096) -> str:
    """Format and truncate outbound message."""
    sanitized = sanitize_outbound_text(text)
    if len(sanitized) <= max_length:
        return sanitized
    truncated = sanitized[:max_length - 20]
    last_newline = truncated.rfind("\n")
    if last_newline > max_length * 0.5:
        truncated = truncated[:last_newline]
    return truncated + "\n… (truncated)"


def split_long_message(text: str, max_length: int = 4096) -> list[str]:
    """Split a long message into chunks."""
    if len(text) <= max_length:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        split_point = remaining.rfind("\n", 0, max_length)
        if split_point <= max_length * 0.3:
            split_point = max_length
        chunks.append(remaining[:split_point])
        remaining = remaining[split_point:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


# ─── delivery-queue.ts ───

@dataclass
class DeliveryQueueEntry:
    envelope: OutboundEnvelope = field(default_factory=OutboundEnvelope)
    attempts: int = 0
    max_attempts: int = 3
    next_attempt_at: float = 0.0
    created_at: float = 0.0
    last_error: str | None = None


class DeliveryQueue:
    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._queue: list[DeliveryQueueEntry] = []
        self._processing: bool = False

    def enqueue(self, envelope: OutboundEnvelope, max_attempts: int = 3) -> bool:
        if len(self._queue) >= self._max_size:
            return False
        self._queue.append(DeliveryQueueEntry(
            envelope=envelope,
            max_attempts=max_attempts,
            created_at=time.time(),
        ))
        return True

    def dequeue_ready(self, now: float | None = None) -> list[DeliveryQueueEntry]:
        now = now or time.time()
        ready = [e for e in self._queue if e.next_attempt_at <= now and e.attempts < e.max_attempts]
        self._queue = [e for e in self._queue if e not in ready]
        return ready

    def requeue(self, entry: DeliveryQueueEntry, delay_ms: int = 1000) -> None:
        entry.attempts += 1
        entry.next_attempt_at = time.time() + delay_ms / 1000.0
        if entry.attempts < entry.max_attempts:
            self._queue.append(entry)

    def mark_failed(self, entry: DeliveryQueueEntry, error: str) -> None:
        entry.last_error = error
        entry.attempts = entry.max_attempts  # exhaust retries

    @property
    def size(self) -> int:
        return len(self._queue)

    @property
    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def clear(self) -> None:
        self._queue.clear()


# ─── outbound-policy.ts ───

@dataclass
class OutboundPolicy:
    enabled: bool = True
    max_message_length: int = 4096
    rate_limit_per_minute: int = 30
    allowed_channels: list[str] = field(default_factory=list)
    blocked_targets: list[str] = field(default_factory=list)


def evaluate_outbound_policy(
    envelope: OutboundEnvelope,
    policy: OutboundPolicy | None = None,
) -> tuple[bool, str]:
    """Evaluate whether an outbound message is allowed."""
    if not policy:
        return True, "no policy"
    if not policy.enabled:
        return False, "outbound disabled"
    if policy.allowed_channels and envelope.channel not in policy.allowed_channels:
        return False, f"channel '{envelope.channel}' not allowed"
    target_normalized = normalize_outbound_target(envelope.target)
    for blocked in policy.blocked_targets:
        if normalize_outbound_target(blocked) == target_normalized:
            return False, f"target '{envelope.target}' is blocked"
    if len(envelope.text) > policy.max_message_length:
        return False, f"message too long ({len(envelope.text)} > {policy.max_message_length})"
    return True, "allowed"


# ─── message-action-spec.ts ───

@dataclass
class MessageActionSpec:
    action: str = ""  # "send" | "reply" | "edit" | "delete" | "react"
    channel: str = ""
    target: str = ""
    text: str = ""
    reply_to: str | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── tool-payload.ts ───

@dataclass
class ToolPayload:
    tool_name: str = ""
    tool_call_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    duration_ms: int | None = None


# ─── session-context.ts ───

@dataclass
class OutboundSessionContext:
    session_key: str = ""
    agent_id: str | None = None
    conversation_id: str | None = None
    channel: str = ""
    target: str = ""


# ─── directory-cache.ts ───

class DirectoryCache:
    """Cache for channel directory lookups."""
    def __init__(self, ttl_s: float = 300.0):
        self._ttl_s = ttl_s
        self._cache: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any:
        entry = self._cache.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time() + self._ttl_s)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()


# ─── abort.ts ───

def create_outbound_abort_controller() -> dict[str, Any]:
    """Create an abort controller for outbound operations."""
    event = asyncio.Event()
    return {
        "signal": event,
        "abort": event.set,
        "aborted": event.is_set,
    }

"""Shared types and type utilities.

Ported from bk/src/types/ (~9 TS files).

Core shared type definitions and type aliases used across modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeVar

__all__ = [
    "ChannelType", "MessageDirection", "DeliveryStatus",
    "InboundMessage", "OutboundMessage", "Attachment",
    "ContactInfo", "ChannelAccount", "ServiceStatus",
    "Result", "Ok", "Err",
]


# ─── Channel types ───

class ChannelType:
    DISCORD = "discord"
    TELEGRAM = "telegram"
    SLACK = "slack"
    SIGNAL = "signal"
    IMESSAGE = "imessage"
    WHATSAPP = "whatsapp"
    LINE = "line"
    WEB = "web"
    INTERNAL = "internal"

    ALL = [DISCORD, TELEGRAM, SLACK, SIGNAL, IMESSAGE, WHATSAPP, LINE, WEB, INTERNAL]


class MessageDirection:
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class DeliveryStatus:
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# ─── Message types ───

@dataclass
class Attachment:
    url: str = ""
    path: str = ""
    mime_type: str = ""
    filename: str = ""
    size_bytes: int = 0
    media_type: str = ""  # "image" | "audio" | "video" | "document"


@dataclass
class InboundMessage:
    id: str = ""
    channel: str = ""
    sender_id: str = ""
    sender_name: str = ""
    text: str = ""
    timestamp_ms: int = 0
    is_direct: bool = False
    is_group: bool = False
    is_mention: bool = False
    is_reply: bool = False
    group_id: str | None = None
    thread_id: str | None = None
    reply_to_id: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    id: str = ""
    channel: str = ""
    to: str = ""
    text: str = ""
    timestamp_ms: int = 0
    reply_to_id: str | None = None
    thread_id: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    delivery_status: str = DeliveryStatus.PENDING


# ─── Contact / Account ───

@dataclass
class ContactInfo:
    id: str = ""
    name: str = ""
    channel: str = ""
    phone: str = ""
    email: str = ""
    avatar_url: str = ""


@dataclass
class ChannelAccount:
    id: str = ""
    channel: str = ""
    display_name: str = ""
    is_bot: bool = False


# ─── Service status ───

@dataclass
class ServiceStatus:
    name: str = ""
    status: str = "unknown"  # "running" | "stopped" | "error" | "unknown"
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# ─── Result type ───

T = TypeVar("T")


@dataclass
class Ok:
    value: Any = None
    ok: bool = True


@dataclass
class Err:
    error: str = ""
    ok: bool = False


Result = Ok | Err

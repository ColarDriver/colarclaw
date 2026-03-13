"""Channels dock — ported from bk/src/channels/dock.ts.

Channel dock definitions: lightweight channel metadata and behavior
for shared code paths (config readers, allowFrom formatting, mention
stripping, threading defaults, group policies).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


# ─── types ───

ChatType = Literal["direct", "group", "channel", "thread"]


@dataclass
class ChannelCapabilities:
    chat_types: list[str] = field(default_factory=list)
    polls: bool = False
    reactions: bool = False
    media: bool = False
    native_commands: bool = False
    threads: bool = False
    block_streaming: bool = False


@dataclass
class ChannelCommandAdapter:
    enforce_owner_for_commands: bool = False
    skip_when_config_empty: bool = False


@dataclass
class ChannelDockStreaming:
    block_streaming_coalesce_defaults: dict[str, int] | None = None


@dataclass
class ChannelThreadingToolContext:
    current_channel_id: str | None = None
    current_thread_ts: str | None = None
    current_message_id: str | int | None = None
    has_replied_ref: Any = None


@dataclass
class ChannelDock:
    id: str = ""
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)
    commands: ChannelCommandAdapter | None = None
    outbound_text_chunk_limit: int | None = None
    streaming: ChannelDockStreaming | None = None
    # Config, groups, mentions, threading adapters are callables stored as dicts
    config: dict[str, Any] | None = None
    groups: dict[str, Any] | None = None
    mentions: dict[str, Any] | None = None
    threading: dict[str, Any] | None = None
    elevated: dict[str, Any] | None = None
    agent_prompt: dict[str, Any] | None = None


# ─── default constants ───

DEFAULT_OUTBOUND_TEXT_CHUNK_LIMIT_4000 = 4000
DEFAULT_BLOCK_STREAMING_COALESCE = {"minChars": 1500, "idleMs": 1000}


# ─── dock definitions (one per core channel) ───

DOCKS: dict[str, ChannelDock] = {
    "telegram": ChannelDock(
        id="telegram",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "group", "channel", "thread"],
            native_commands=True,
            block_streaming=True,
        ),
        outbound_text_chunk_limit=4000,
    ),
    "whatsapp": ChannelDock(
        id="whatsapp",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "group"],
            polls=True, reactions=True, media=True,
        ),
        commands=ChannelCommandAdapter(enforce_owner_for_commands=True, skip_when_config_empty=True),
        outbound_text_chunk_limit=4000,
    ),
    "discord": ChannelDock(
        id="discord",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "channel", "thread"],
            polls=True, reactions=True, media=True,
            native_commands=True, threads=True,
        ),
        outbound_text_chunk_limit=2000,
        streaming=ChannelDockStreaming(block_streaming_coalesce_defaults=DEFAULT_BLOCK_STREAMING_COALESCE),
    ),
    "irc": ChannelDock(
        id="irc",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "group"],
            media=True, block_streaming=True,
        ),
        outbound_text_chunk_limit=350,
        streaming=ChannelDockStreaming(block_streaming_coalesce_defaults={"minChars": 300, "idleMs": 1000}),
    ),
    "googlechat": ChannelDock(
        id="googlechat",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "group", "thread"],
            reactions=True, media=True, threads=True,
            block_streaming=True,
        ),
        outbound_text_chunk_limit=4000,
    ),
    "slack": ChannelDock(
        id="slack",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "channel", "thread"],
            reactions=True, media=True,
            native_commands=True, threads=True,
        ),
        outbound_text_chunk_limit=4000,
        streaming=ChannelDockStreaming(block_streaming_coalesce_defaults=DEFAULT_BLOCK_STREAMING_COALESCE),
    ),
    "signal": ChannelDock(
        id="signal",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "group"],
            reactions=True, media=True,
        ),
        outbound_text_chunk_limit=4000,
        streaming=ChannelDockStreaming(block_streaming_coalesce_defaults=DEFAULT_BLOCK_STREAMING_COALESCE),
    ),
    "imessage": ChannelDock(
        id="imessage",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "group"],
            reactions=True, media=True,
        ),
        outbound_text_chunk_limit=4000,
    ),
    "line": ChannelDock(
        id="line",
        capabilities=ChannelCapabilities(
            chat_types=["direct", "group"],
            media=True,
        ),
        outbound_text_chunk_limit=5000,
    ),
}


# ─── dock resolution ───

def list_channel_docks() -> list[ChannelDock]:
    """Return ordered list of all channel docks."""
    from .registry import CHAT_CHANNEL_ORDER
    return [DOCKS[ch] for ch in CHAT_CHANNEL_ORDER if ch in DOCKS]


def get_channel_dock(channel_id: str) -> ChannelDock | None:
    """Get the dock definition for a specific channel."""
    return DOCKS.get(channel_id)

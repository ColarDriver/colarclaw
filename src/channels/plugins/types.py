"""Channels plugin types — ported from bk/src/channels/plugins/types.core.ts,
types.ts, types.adapters.ts, types.plugin.ts.

Core type definitions for the channel plugin system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol


# ─── core IDs ───

ChannelId = str  # ChatChannelId or plugin-provided ID


# ─── types.core.ts ───

ChatType = Literal["direct", "group", "channel", "thread"]

ChannelOutboundTargetMode = Literal["explicit", "implicit", "heartbeat"]


@dataclass
class ChannelMeta:
    id: str = ""
    label: str = ""
    selection_label: str = ""
    docs_path: str = ""
    docs_label: str = ""
    blurb: str = ""
    order: int | None = None
    aliases: list[str] = field(default_factory=list)
    selection_docs_prefix: str = ""
    selection_docs_omit_label: bool = False
    selection_extras: list[str] = field(default_factory=list)
    detail_label: str = ""
    system_image: str = ""
    show_configured: bool = False
    quickstart_allow_from: bool = False
    force_account_binding: bool = False
    prefer_session_lookup: bool = False
    prefer_over: list[str] = field(default_factory=list)


@dataclass
class ChannelCapabilities:
    chat_types: list[str] = field(default_factory=list)
    polls: bool = False
    reactions: bool = False
    edit: bool = False
    unsend: bool = False
    reply: bool = False
    effects: bool = False
    group_management: bool = False
    threads: bool = False
    media: bool = False
    native_commands: bool = False
    block_streaming: bool = False


@dataclass
class ChannelSetupInput:
    name: str = ""
    token: str = ""
    token_file: str = ""
    bot_token: str = ""
    app_token: str = ""
    signal_number: str = ""
    cli_path: str = ""
    db_path: str = ""
    service: str = ""
    region: str = ""
    auth_dir: str = ""
    http_url: str = ""
    http_host: str = ""
    http_port: str = ""
    webhook_path: str = ""
    webhook_url: str = ""
    audience_type: str = ""
    audience: str = ""
    use_env: bool = False
    homeserver: str = ""
    user_id: str = ""
    access_token: str = ""
    password: str = ""
    device_name: str = ""
    initial_sync_limit: int = 0
    ship: str = ""
    url: str = ""
    code: str = ""
    group_channels: list[str] = field(default_factory=list)
    dm_allowlist: list[str] = field(default_factory=list)
    auto_discover_channels: bool = False


@dataclass
class ChannelStatusIssue:
    channel: str = ""
    account_id: str = ""
    kind: str = ""  # "intent" | "permissions" | "config" | "auth" | "runtime"
    message: str = ""
    fix: str = ""


ChannelAccountState = Literal[
    "linked", "not linked", "configured",
    "not configured", "enabled", "disabled",
]


@dataclass
class ChannelAccountSnapshot:
    account_id: str = ""
    name: str = ""
    enabled: bool | None = None
    configured: bool | None = None
    linked: bool | None = None
    running: bool | None = None
    connected: bool | None = None
    restart_pending: bool = False
    reconnect_attempts: int = 0
    last_connected_at: float | None = None
    last_message_at: float | None = None
    last_event_at: float | None = None
    last_error: str | None = None
    busy: bool = False
    active_runs: int = 0
    mode: str = ""
    dm_policy: str = ""
    allow_from: list[str] = field(default_factory=list)
    token_source: str = ""
    token_status: str = ""
    probe: Any = None


@dataclass
class ChannelThreadingContext:
    channel: str = ""
    from_: str = ""
    to: str = ""
    chat_type: str = ""
    current_message_id: str | int | None = None
    reply_to_id: str = ""
    reply_to_id_full: str = ""
    thread_label: str = ""
    message_thread_id: str | int | None = None
    native_channel_id: str = ""


@dataclass
class ChannelThreadingToolContext:
    current_channel_id: str | None = None
    current_channel_provider: str | None = None
    current_thread_ts: str | None = None
    current_message_id: str | int | None = None
    reply_to_mode: str | None = None
    has_replied_ref: Any = None
    skip_cross_context_decoration: bool = False


ChannelDirectoryEntryKind = Literal["user", "group", "channel"]


@dataclass
class ChannelDirectoryEntry:
    kind: str = "user"  # ChannelDirectoryEntryKind
    id: str = ""
    name: str = ""
    handle: str = ""
    avatar_url: str = ""
    rank: int = 0
    raw: Any = None


@dataclass
class ChannelSecurityDmPolicy:
    policy: str = ""
    allow_from: list[str | int] | None = None
    policy_path: str = ""
    allow_from_path: str = ""
    approve_hint: str = ""


# ─── types.plugin.ts ───

@dataclass
class ChannelPlugin:
    """A registered channel plugin."""
    id: str = ""
    meta: ChannelMeta = field(default_factory=ChannelMeta)
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)
    # Adapters stored as dicts or callable references
    commands: dict[str, Any] | None = None
    outbound: dict[str, Any] | None = None
    streaming: dict[str, Any] | None = None
    elevated: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    groups: dict[str, Any] | None = None
    mentions: dict[str, Any] | None = None
    threading: dict[str, Any] | None = None
    agent_prompt: dict[str, Any] | None = None
    messaging: dict[str, Any] | None = None
    message_actions: dict[str, Any] | None = None


# ─── types.adapters.ts (summary) ───

@dataclass
class ChannelConfigAdapter:
    """Adapter for resolving channel configuration."""
    resolve_allow_from: Callable | None = None
    format_allow_from: Callable | None = None
    resolve_default_to: Callable | None = None


@dataclass
class ChannelGroupAdapter:
    """Adapter for group policy resolution."""
    resolve_require_mention: Callable | None = None
    resolve_tool_policy: Callable | None = None
    resolve_group_intro_hint: Callable | None = None


@dataclass
class ChannelElevatedAdapter:
    """Adapter for elevated access fallback."""
    allow_from_fallback: Callable | None = None


# ─── BaseProbeResult / BaseTokenResolution ───

@dataclass
class BaseProbeResult:
    ok: bool = True
    error: str | None = None


@dataclass
class BaseTokenResolution:
    token: str = ""
    source: str = ""

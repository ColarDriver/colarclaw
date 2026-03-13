"""Channels package — ported from bk/src/channels/.

Channel registry, configuration matching, target parsing, allowlists,
typing indicators, status reactions, plugin infrastructure, and
per-channel implementations.

Submodules:
    registry        — channel metadata, IDs, aliases, normalization
    config          — channel config matching, slug normalization
    targets         — messaging target parsing and normalization
    allow_from      — allowlist resolution and matching
    typing          — typing indicator lifecycle and keepalive
    reactions       — status reaction controller (emoji-based agent status)
    session         — inbound session recording and routing
    dock            — channel dock definitions (capabilities, commands)
    model_overrides — per-channel model override resolution
    gating          — command and mention gating
    run_state       — run state machine and heartbeat
    thread_bindings — thread binding policy and timeout
    location        — location types and formatting
    account         — account snapshots and summaries
    transport       — transport-level stall watchdog
    draft_stream    — block streaming coalesced output
    reply_prefix    — reply prefix context and formatting
    telegram        — Telegram API helpers
    logging         — channel-scoped logging

Subpackages:
    plugins         — channel plugin types, catalog, adapters, normalize,
                      outbound, actions, status issues, onboarding,
                      group mentions, directory config, message actions
"""
from .registry import (
    CHAT_CHANNEL_ORDER,
    CHANNEL_IDS,
    ChatChannelId,
    ChannelMeta,
    normalize_chat_channel_id,
    normalize_channel_id,
    get_chat_channel_meta,
    list_chat_channels,
)
from .config import (
    normalize_channel_slug,
    resolve_channel_entry_match,
    resolve_nested_allowlist_decision,
)
from .targets import (
    MessagingTarget,
    normalize_target_id,
    build_messaging_target,
)

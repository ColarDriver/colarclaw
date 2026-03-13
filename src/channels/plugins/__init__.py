"""Channels plugins — ported from bk/src/channels/plugins/.

Channel plugin infrastructure: types, catalog, config helpers,
adapter definitions, per-channel implementations.

Submodules:
    types               — core plugin types (ChannelPlugin, capabilities, etc.)
    catalog             — registry, status, media limits, helpers
    normalize           — per-channel target normalization
    outbound            — outbound adapter loading + send
    outbound_channels   — per-channel outbound message adapters
    actions             — action dispatch + validation
    actions_channels    — per-channel action handlers
    status_issues       — status issue detection helpers
    status_issues_channels — per-channel status issue detection
    onboarding          — onboarding flows + channel access
    onboarding_helpers  — shared onboarding helpers
    onboarding_channels — per-channel onboarding adapters
    onboarding_access   — channel access configuration
    onboarding_types    — onboarding type definitions
    setup_helpers       — account config promotion helpers
    group_mentions      — per-channel group mention policy
    group_policy_warnings — group policy validation
    config_helpers      — config reading/writing utilities
    directory_config    — directory cache, filtering, ranking
    message_actions     — message action names and gating
    agent_tools         — agent tools (WhatsApp login, etc.)
"""
from .types import (
    ChannelPlugin,
    ChannelId,
    ChannelMeta,
    ChannelCapabilities,
    ChannelSetupInput,
    ChannelAccountSnapshot,
    ChannelStatusIssue,
    ChannelDirectoryEntry,
    ChannelThreadingContext,
    ChannelThreadingToolContext,
)
from .catalog import (
    ChannelPluginRegistry,
    get_active_plugin_registry,
    set_active_plugin_registry,
    assess_channel_status,
    resolve_channel_media_max_bytes,
)

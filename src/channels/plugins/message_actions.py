"""Channels plugins.message_actions — ported from bk/src/channels/plugins/message-actions.ts,
message-action-names.ts, account-action-gate.ts, slack.actions.ts, bluebubbles-actions.ts,
whatsapp-heartbeat.ts, whatsapp-shared.ts.

Message action definitions, action name registry, account-level action gating,
and channel-specific action/heartbeat helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


# ─── message-action-names.ts ───

CHANNEL_MESSAGE_ACTION_NAMES = [
    "send", "sendMedia", "react", "unreact", "poll",
    "editMessage", "deleteMessage", "unsendMessage",
    "pinMessage", "unpinMessage",
    "createThread", "addThreadMember",
    "setTyping", "markRead",
    "guildAdmin",
    "buttons", "card",
]

ChannelMessageActionName = Literal[
    "send", "sendMedia", "react", "unreact", "poll",
    "editMessage", "deleteMessage", "unsendMessage",
    "pinMessage", "unpinMessage",
    "createThread", "addThreadMember",
    "setTyping", "markRead",
    "guildAdmin",
    "buttons", "card",
]


# ─── message-actions.ts ───

@dataclass
class MessageActionSecurity:
    require_owner: bool = False
    audit_log: bool = True


def validate_message_action_params(
    action: str,
    params: dict[str, Any],
) -> str | None:
    """Validate action params, returning error string if invalid."""
    if action == "send" and not params.get("to"):
        return "send action requires 'to' parameter"
    if action == "react" and not params.get("emoji"):
        return "react action requires 'emoji' parameter"
    if action == "poll":
        if not params.get("question"):
            return "poll action requires 'question'"
        if not params.get("options") or len(params["options"]) < 2:
            return "poll action requires at least 2 options"
    return None


def is_destructive_action(action: str) -> bool:
    """Check if an action is destructive (delete, ban, etc.)."""
    return action in (
        "deleteMessage", "unsendMessage",
        "kickMember", "banMember",
    )


# ─── account-action-gate.ts ───

def resolve_account_action_gate(
    cfg: dict[str, Any],
    channel: str,
    account_id: str = "",
    action: str = "",
) -> bool:
    """Check if an action is allowed for the given account."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})

    # Check channel-level action gate
    disabled_actions = channel_cfg.get("disabledActions", [])
    if action in disabled_actions:
        return False

    # Check account-level gate
    if account_id:
        acct = channel_cfg.get("accounts", {}).get(account_id, {})
        acct_disabled = acct.get("disabledActions", [])
        if action in acct_disabled:
            return False

    return True


# ─── slack.actions.ts ───

SLACK_SUPPORTED_ACTIONS = ["send", "sendMedia", "react", "unreact", "buttons"]


def list_slack_actions(cfg: dict[str, Any] | None = None) -> list[str]:
    return list(SLACK_SUPPORTED_ACTIONS)


# ─── bluebubbles-actions.ts ───

BLUEBUBBLES_SUPPORTED_ACTIONS = ["send", "sendMedia", "react"]


def list_bluebubbles_actions(cfg: dict[str, Any] | None = None) -> list[str]:
    return list(BLUEBUBBLES_SUPPORTED_ACTIONS)


# ─── whatsapp-shared.ts ───

WHATSAPP_STICKER_MAX_KB = 100
WHATSAPP_MEDIA_CAPTION_LIMIT = 1024


def normalize_whatsapp_jid(jid: str) -> str:
    """Normalize a WhatsApp JID."""
    return jid.strip().lower()


# ─── whatsapp-heartbeat.ts ───

DEFAULT_WHATSAPP_HEARTBEAT_INTERVAL_MS = 30_000
DEFAULT_WHATSAPP_RECONNECT_DELAY_MS = 5_000


@dataclass
class WhatsAppHeartbeatConfig:
    interval_ms: int = DEFAULT_WHATSAPP_HEARTBEAT_INTERVAL_MS
    reconnect_delay_ms: int = DEFAULT_WHATSAPP_RECONNECT_DELAY_MS
    max_reconnect_attempts: int = 10


def resolve_whatsapp_heartbeat_config(
    cfg: dict[str, Any],
) -> WhatsAppHeartbeatConfig:
    """Resolve WhatsApp heartbeat config."""
    wa_cfg = cfg.get("channels", {}).get("whatsapp", {})
    heartbeat = wa_cfg.get("heartbeat", {})
    return WhatsAppHeartbeatConfig(
        interval_ms=heartbeat.get("intervalMs", DEFAULT_WHATSAPP_HEARTBEAT_INTERVAL_MS),
        reconnect_delay_ms=heartbeat.get("reconnectDelayMs", DEFAULT_WHATSAPP_RECONNECT_DELAY_MS),
        max_reconnect_attempts=heartbeat.get("maxReconnectAttempts", 10),
    )

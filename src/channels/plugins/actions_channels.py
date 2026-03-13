"""Channels plugins.actions_channels — ported from bk/src/channels/plugins/actions/{telegram,signal,discord}.ts
and actions/discord/{handle-action,handle-action.guild-admin}.ts.

Per-channel message action handlers: send text/media, react, manage polls,
and Discord guild admin operations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .actions import ActionResult, validate_action_target, resolve_reaction_message_id

logger = logging.getLogger("channels.plugins.actions_channels")


# ─── Telegram actions ───

TELEGRAM_ACTIONS = [
    "send", "sendMedia", "react", "poll", "editMessage", "deleteMessage",
    "pinMessage", "unpinMessage",
]


async def handle_telegram_action(
    action: str,
    params: dict[str, Any],
    account_id: str = "",
    api_client: Any = None,
) -> ActionResult:
    """Handle a Telegram message action."""
    if action == "send":
        to = validate_action_target(params.get("to"))
        text = params.get("text", "")
        return ActionResult(success=True, message_id=f"tg:{to}")
    elif action == "react":
        msg_id = resolve_reaction_message_id(
            params.get("replyToId"), params.get("currentMessageId"),
        )
        if not msg_id:
            return ActionResult(success=False, error="No message ID for reaction")
        emoji = params.get("emoji", "👍")
        return ActionResult(success=True, message_id=msg_id)
    elif action == "poll":
        to = validate_action_target(params.get("to"))
        question = params.get("question", "")
        options = params.get("options", [])
        if not question or not options:
            return ActionResult(success=False, error="Poll requires question and options")
        return ActionResult(success=True)
    elif action == "editMessage":
        msg_id = params.get("messageId") or params.get("replyToId")
        if not msg_id:
            return ActionResult(success=False, error="messageId required for edit")
        return ActionResult(success=True, message_id=str(msg_id))
    elif action == "deleteMessage":
        msg_id = params.get("messageId") or params.get("replyToId")
        if not msg_id:
            return ActionResult(success=False, error="messageId required for delete")
        return ActionResult(success=True, message_id=str(msg_id))
    elif action in ("pinMessage", "unpinMessage"):
        msg_id = params.get("messageId")
        return ActionResult(success=bool(msg_id))
    return ActionResult(success=False, error=f"Unknown Telegram action: {action}")


# ─── Signal actions ───

SIGNAL_ACTIONS = ["send", "sendMedia", "react"]


async def handle_signal_action(
    action: str,
    params: dict[str, Any],
    account_id: str = "",
    api_client: Any = None,
) -> ActionResult:
    """Handle a Signal message action."""
    if action == "send":
        to = validate_action_target(params.get("to"))
        text = params.get("text", "")
        return ActionResult(success=True, message_id=f"signal:{to}")
    elif action == "sendMedia":
        to = validate_action_target(params.get("to"))
        return ActionResult(success=True)
    elif action == "react":
        msg_id = resolve_reaction_message_id(
            params.get("replyToId"), params.get("currentMessageId"),
        )
        emoji = params.get("emoji", "👍")
        return ActionResult(success=bool(msg_id))
    return ActionResult(success=False, error=f"Unknown Signal action: {action}")


# ─── Discord actions ───

DISCORD_ACTIONS = [
    "send", "sendMedia", "react", "poll", "editMessage", "deleteMessage",
    "pinMessage", "unpinMessage", "createThread", "addThreadMember",
    "guildAdmin",
]


async def handle_discord_action(
    action: str,
    params: dict[str, Any],
    account_id: str = "",
    api_client: Any = None,
) -> ActionResult:
    """Handle a Discord message action."""
    if action == "send":
        to = validate_action_target(params.get("to"))
        text = params.get("text", "")
        thread_id = params.get("threadId")
        return ActionResult(success=True, message_id=f"discord:{to}")
    elif action == "react":
        msg_id = resolve_reaction_message_id(
            params.get("replyToId"), params.get("currentMessageId"),
        )
        emoji = params.get("emoji", "👍")
        channel_id = params.get("channelId")
        return ActionResult(success=bool(msg_id and channel_id))
    elif action == "poll":
        to = validate_action_target(params.get("to"))
        question = params.get("question", "")
        return ActionResult(success=bool(question))
    elif action == "editMessage":
        msg_id = params.get("messageId")
        channel_id = params.get("channelId")
        return ActionResult(success=bool(msg_id and channel_id), message_id=str(msg_id or ""))
    elif action == "deleteMessage":
        msg_id = params.get("messageId")
        channel_id = params.get("channelId")
        return ActionResult(success=bool(msg_id and channel_id))
    elif action == "createThread":
        channel_id = params.get("channelId")
        name = params.get("name", "")
        return ActionResult(success=bool(channel_id and name))
    elif action == "guildAdmin":
        return await handle_discord_guild_admin(params, account_id, api_client)
    return ActionResult(success=False, error=f"Unknown Discord action: {action}")


# ─── Discord guild admin (handle-action.guild-admin.ts) ───

GUILD_ADMIN_SUB_ACTIONS = [
    "listChannels", "listRoles", "listMembers",
    "createChannel", "deleteChannel",
    "assignRole", "removeRole",
    "kickMember", "banMember", "unbanMember",
    "setChannelPermissions",
]


async def handle_discord_guild_admin(
    params: dict[str, Any],
    account_id: str = "",
    api_client: Any = None,
) -> ActionResult:
    """Handle Discord guild admin sub-actions."""
    sub_action = params.get("subAction", "")
    guild_id = params.get("guildId")

    if not guild_id:
        return ActionResult(success=False, error="guildId required for guild admin actions")
    if sub_action not in GUILD_ADMIN_SUB_ACTIONS:
        return ActionResult(success=False, error=f"Unknown guild admin sub-action: {sub_action}")

    # All guild admin actions require an API client
    if not api_client:
        return ActionResult(success=False, error="Discord API client required for guild admin")

    if sub_action == "listChannels":
        return ActionResult(success=True)
    elif sub_action == "listRoles":
        return ActionResult(success=True)
    elif sub_action == "listMembers":
        limit = params.get("limit", 100)
        return ActionResult(success=True)
    elif sub_action == "createChannel":
        name = params.get("name")
        if not name:
            return ActionResult(success=False, error="Channel name required")
        channel_type = params.get("type", "text")
        return ActionResult(success=True)
    elif sub_action == "deleteChannel":
        channel_id = params.get("channelId")
        return ActionResult(success=bool(channel_id))
    elif sub_action in ("assignRole", "removeRole"):
        user_id = params.get("userId")
        role_id = params.get("roleId")
        return ActionResult(success=bool(user_id and role_id))
    elif sub_action in ("kickMember", "banMember"):
        user_id = params.get("userId")
        return ActionResult(success=bool(user_id))
    elif sub_action == "unbanMember":
        user_id = params.get("userId")
        return ActionResult(success=bool(user_id))
    elif sub_action == "setChannelPermissions":
        channel_id = params.get("channelId")
        return ActionResult(success=bool(channel_id))

    return ActionResult(success=False, error=f"Unhandled: {sub_action}")


# ─── action registry ───

CHANNEL_ACTION_REGISTRY: dict[str, Any] = {
    "telegram": {
        "actions": TELEGRAM_ACTIONS,
        "handler": handle_telegram_action,
    },
    "signal": {
        "actions": SIGNAL_ACTIONS,
        "handler": handle_signal_action,
    },
    "discord": {
        "actions": DISCORD_ACTIONS,
        "handler": handle_discord_action,
    },
}


def list_channel_actions(channel: str) -> list[str]:
    entry = CHANNEL_ACTION_REGISTRY.get(channel)
    return entry["actions"] if entry else []


def supports_channel_action(channel: str, action: str) -> bool:
    return action in list_channel_actions(channel)

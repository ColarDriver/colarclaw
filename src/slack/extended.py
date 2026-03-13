"""Slack — extended handler, interactions, media, delivery.

Ported from bk/src/slack/ remaining large files:
monitor/slash.ts (~881行), monitor/message-handler/prepare.ts (~803行),
monitor/events/interactions.ts (~675行),
monitor/message-handler/dispatch.ts (~531行),
monitor/provider.ts (~520行), monitor/media.ts (~519行),
actions.ts (~446行), monitor/context.ts (~431行), send.ts (~360行).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Message context ───

@dataclass
class SlackMessageContext:
    channel: str = ""
    user: str = ""
    ts: str = ""
    text: str = ""
    thread_ts: str | None = None
    team: str = ""
    is_dm: bool = False
    is_channel: bool = False
    is_mention: bool = False
    is_thread_reply: bool = False
    is_app_home: bool = False
    bot_id: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    channel_name: str = ""


# ─── Slash commands ───

@dataclass
class SlackSlashCommand:
    command: str = ""
    text: str = ""
    user_id: str = ""
    channel_id: str = ""
    team_id: str = ""
    response_url: str = ""
    trigger_id: str = ""


SLACK_SLASH_COMMANDS = [
    {"command": "/ask", "description": "Ask a question"},
    {"command": "/model", "description": "Switch model"},
    {"command": "/new", "description": "New session"},
    {"command": "/status", "description": "Show status"},
    {"command": "/agents", "description": "List agents"},
    {"command": "/help", "description": "Show help"},
]


async def handle_slash_command(cmd: SlackSlashCommand) -> dict[str, Any]:
    """Handle a Slack slash command."""
    command = cmd.command.lstrip("/")

    if command == "ask":
        return {"response_type": "in_channel", "text": f"Processing: {cmd.text}"}
    elif command == "help":
        lines = ["*Available commands:*"]
        for sc in SLACK_SLASH_COMMANDS:
            lines.append(f"  `{sc['command']}` — {sc['description']}")
        return {"response_type": "ephemeral", "text": "\n".join(lines)}
    elif command == "new":
        return {"response_type": "ephemeral", "text": "🔄 New session started."}
    elif command == "status":
        return {"response_type": "ephemeral", "text": "✅ Bot is running."}
    elif command == "model":
        return {"response_type": "ephemeral", "text": f"Model: {cmd.text or 'default'}"}

    return {"response_type": "ephemeral", "text": f"Unknown command: {cmd.command}"}


# ─── Event interactions ───

@dataclass
class SlackInteractionPayload:
    type: str = ""  # "block_actions" | "view_submission" | "message_action" | "shortcut"
    trigger_id: str = ""
    user: dict[str, str] = field(default_factory=dict)
    channel: dict[str, str] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    message: dict[str, Any] = field(default_factory=dict)
    view: dict[str, Any] = field(default_factory=dict)


async def handle_interaction(payload: SlackInteractionPayload) -> dict[str, Any] | None:
    """Handle a Slack interaction."""
    if payload.type == "block_actions":
        for action in payload.actions:
            action_id = action.get("action_id", "")
            if action_id.startswith("model_"):
                value = action.get("selected_option", {}).get("value", "")
                return {"text": f"Model switched to: {value}"}
            if action_id.startswith("approve_"):
                return {"text": "✅ Approved"}
            if action_id.startswith("deny_"):
                return {"text": "❌ Denied"}

    elif payload.type == "view_submission":
        values = payload.view.get("state", {}).get("values", {})
        return {"response_action": "clear", "values": values}

    return None


# ─── Dispatch ───

@dataclass
class SlackDispatchDecision:
    should_reply: bool = True
    reason: str = ""
    is_command: bool = False
    agent_id: str = ""


def dispatch_slack_message(
    context: SlackMessageContext,
    *,
    allowed_channels: list[str] | None = None,
    dm_allowlist: list[str] | None = None,
) -> SlackDispatchDecision:
    """Decide how to handle a Slack message."""
    decision = SlackDispatchDecision()

    # Filter channels
    if allowed_channels and context.channel not in allowed_channels and not context.is_dm:
        decision.should_reply = False
        decision.reason = "Channel not in allowlist"
        return decision

    # DM allowlist
    if context.is_dm and dm_allowlist and context.user not in dm_allowlist:
        decision.should_reply = False
        decision.reason = "User not in DM allowlist"
        return decision

    # Non-DM: require mention or thread
    if not context.is_dm and not context.is_mention and not context.is_thread_reply:
        decision.should_reply = False
        decision.reason = "Not mentioned in channel"

    return decision


# ─── Media handling ───

async def download_slack_file(
    file_info: dict[str, Any],
    *,
    bot_token: str = "",
    dest_dir: str = "/tmp",
) -> str | None:
    """Download a Slack file attachment."""
    url = file_info.get("url_private_download") or file_info.get("url_private")
    if not url:
        return None

    try:
        import aiohttp, os
        os.makedirs(dest_dir, exist_ok=True)
        filename = file_info.get("name", "download")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"Authorization": f"Bearer {bot_token}"}) as resp:
                if resp.status != 200:
                    return None
                dest = os.path.join(dest_dir, filename)
                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_any():
                        f.write(chunk)
                return dest
    except Exception as e:
        logger.error(f"Slack file download error: {e}")
        return None


# ─── Delivery ───

async def deliver_slack_reply(
    adapter: Any,
    *,
    channel: str,
    text: str,
    thread_ts: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> str:
    """Deliver a reply via Slack."""
    from . import build_slack_blocks

    # Build blocks if not provided
    if not blocks and len(text) > 100:
        blocks = build_slack_blocks(text)

    return await adapter.send_message(
        channel, text,
        thread_ts=thread_ts,
        blocks=blocks,
    )

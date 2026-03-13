"""Slack — deep: event handler, workspace, home tab, modal, message context.

Covers: monitor/provider.ts (~520行), monitor/context.ts (~431行),
actions.ts (~446行), send.ts (~360行) full depth,
monitor/media.ts (~519行), additional interactions/home.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Request verification ───

def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
) -> bool:
    """Verify Slack request signature."""
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    expected = "v0=" + hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


# ─── Message context (full) ───

@dataclass
class SlackFullContext:
    """Full context for a Slack event."""
    event_type: str = ""
    team_id: str = ""
    channel: str = ""
    channel_name: str = ""
    channel_type: str = ""  # "channel" | "group" | "im" | "mpim"
    user: str = ""
    user_name: str = ""
    ts: str = ""
    text: str = ""
    thread_ts: str | None = None
    is_dm: bool = False
    is_mention: bool = False
    is_thread: bool = False
    is_app_home: bool = False
    bot_user_id: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    reaction: str = ""
    edited: bool = False


def build_context_from_event(event: dict[str, Any], *, bot_user_id: str = "") -> SlackFullContext:
    """Build full context from a Slack event payload."""
    ctx = SlackFullContext()
    ctx.event_type = event.get("type", "")
    ctx.channel = event.get("channel", "")
    ctx.channel_type = event.get("channel_type", "")
    ctx.user = event.get("user", "")
    ctx.ts = event.get("ts", "")
    ctx.text = event.get("text", "")
    ctx.thread_ts = event.get("thread_ts")
    ctx.is_dm = ctx.channel_type == "im"
    ctx.is_thread = bool(ctx.thread_ts)
    ctx.bot_user_id = bot_user_id
    ctx.files = event.get("files", [])
    ctx.attachments = event.get("attachments", [])
    ctx.blocks = event.get("blocks", [])
    ctx.edited = bool(event.get("edited") or event.get("subtype") == "message_changed")

    # Check mention
    if bot_user_id:
        ctx.is_mention = f"<@{bot_user_id}>" in (ctx.text or "")

    return ctx


# ─── Event dispatcher ───

class SlackEventDispatcher:
    """Dispatches Slack events to handlers."""

    def __init__(
        self,
        *,
        allowed_channels: list[str] | None = None,
        dm_allowlist: list[str] | None = None,
        blocked_users: list[str] | None = None,
        require_mention: bool = True,
    ):
        self._allowed_channels = set(allowed_channels or [])
        self._dm_allowlist = set(dm_allowlist or [])
        self._blocked = set(blocked_users or [])
        self._require_mention = require_mention

    def should_process(self, ctx: SlackFullContext) -> tuple[bool, str]:
        if ctx.user in self._blocked:
            return False, "blocked"
        if ctx.is_dm:
            if self._dm_allowlist and ctx.user not in self._dm_allowlist:
                return False, "dm_not_allowed"
            return True, "dm"
        if self._allowed_channels and ctx.channel not in self._allowed_channels:
            return False, "channel_not_allowed"
        if self._require_mention and not ctx.is_mention and not ctx.is_thread:
            return False, "not_mentioned"
        return True, "ok"


# ─── Actions / Interactivity ───

@dataclass
class SlackAction:
    action_id: str = ""
    type: str = ""
    value: str = ""
    selected_option: str = ""
    block_id: str = ""
    trigger_id: str = ""


def parse_action_payload(payload: dict[str, Any]) -> list[SlackAction]:
    """Parse actions from a Slack interaction payload."""
    actions = []
    for raw in payload.get("actions", []):
        actions.append(SlackAction(
            action_id=raw.get("action_id", ""),
            type=raw.get("type", ""),
            value=raw.get("value", ""),
            selected_option=raw.get("selected_option", {}).get("value", ""),
            block_id=raw.get("block_id", ""),
            trigger_id=payload.get("trigger_id", ""),
        ))
    return actions


# ─── Modal builder ───

def build_modal(
    title: str,
    blocks: list[dict[str, Any]],
    *,
    callback_id: str = "",
    submit_text: str = "Submit",
    close_text: str = "Cancel",
) -> dict[str, Any]:
    """Build a Slack modal view."""
    return {
        "type": "modal",
        "callback_id": callback_id or "modal_" + title.lower().replace(" ", "_"),
        "title": {"type": "plain_text", "text": title[:24]},
        "submit": {"type": "plain_text", "text": submit_text},
        "close": {"type": "plain_text", "text": close_text},
        "blocks": blocks,
    }


def build_input_block(
    label: str,
    action_id: str,
    *,
    placeholder: str = "",
    multiline: bool = False,
    optional: bool = False,
) -> dict[str, Any]:
    """Build a Slack input block for modals."""
    element: dict[str, Any] = {
        "type": "plain_text_input",
        "action_id": action_id,
        "multiline": multiline,
    }
    if placeholder:
        element["placeholder"] = {"type": "plain_text", "text": placeholder}
    return {
        "type": "input",
        "label": {"type": "plain_text", "text": label},
        "element": element,
        "optional": optional,
    }


# ─── Home tab ───

def build_home_tab(
    *,
    status: str = "online",
    model: str = "",
    session_count: int = 0,
    channels: list[str] = [],
) -> dict[str, Any]:
    """Build App Home tab view."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🤖 OpenClaw"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Status:* {status}\n*Model:* {model}\n*Sessions:* {session_count}"},
        },
    ]

    if channels:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Connected Channels:*\n" + "\n".join(f"• {ch}" for ch in channels)},
        })

    blocks.append({
        "type": "actions",
        "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "🔄 New Session"}, "action_id": "new_session"},
            {"type": "button", "text": {"type": "plain_text", "text": "⚙️ Settings"}, "action_id": "settings"},
        ],
    })

    return {"type": "home", "blocks": blocks}


# ─── Send pipeline (full) ───

async def send_slack_message(
    adapter: Any,
    *,
    channel: str,
    text: str,
    thread_ts: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    unfurl_links: bool = False,
    unfurl_media: bool = True,
    reply_broadcast: bool = False,
) -> str | None:
    """Full Slack send pipeline."""
    from . import build_slack_blocks

    # Auto-build blocks for rich messages
    if not blocks and len(text) > 200:
        blocks = build_slack_blocks(text)

    return await adapter.send_message(
        channel, text,
        thread_ts=thread_ts,
        blocks=blocks,
    )


async def update_slack_message(
    adapter: Any,
    *,
    channel: str,
    ts: str,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    """Update an existing Slack message."""
    return await adapter.update_message(channel, ts, text, blocks=blocks)


# ─── Media download ───

async def download_slack_files(
    files: list[dict[str, Any]],
    *,
    bot_token: str,
    dest_dir: str = "/tmp",
) -> list[str]:
    """Download multiple Slack file attachments."""
    from .extended import download_slack_file
    paths = []
    for f in files:
        path = await download_slack_file(f, bot_token=bot_token, dest_dir=dest_dir)
        if path:
            paths.append(path)
    return paths


# ─── Slack text utilities ───

def strip_slack_mention(text: str, bot_user_id: str) -> str:
    """Remove bot mention from Slack text."""
    return re.sub(rf"<@{re.escape(bot_user_id)}>\s*", "", text).strip()


def slack_link(url: str, label: str = "") -> str:
    """Build a Slack link."""
    if label:
        return f"<{url}|{label}>"
    return f"<{url}>"


def slack_user_mention(user_id: str) -> str:
    return f"<@{user_id}>"


def slack_channel_mention(channel_id: str) -> str:
    return f"<#{channel_id}>"

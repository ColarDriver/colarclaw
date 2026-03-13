"""Telegram — extended bot handlers, delivery, threads, commands.

Ported from bk/src/telegram/ remaining large files:
bot-handlers.ts (~1565行), send.ts (~1269行),
bot-native-commands.ts (~868行), bot-message-dispatch.ts (~807行),
thread-bindings.ts (~726行), bot/delivery.replies.ts (~661行),
bot/helpers.ts (~607行), bot-message-context.ts (~473行),
lane-delivery-text-deliverer.ts (~463行).
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
class TelegramMessageContext:
    """Rich context for a Telegram message being processed."""
    chat_id: int = 0
    message_id: int = 0
    user_id: int = 0
    user_name: str = ""
    text: str = ""
    is_group: bool = False
    is_private: bool = False
    is_supergroup: bool = False
    is_channel: bool = False
    is_reply: bool = False
    is_forward: bool = False
    reply_to_id: int | None = None
    thread_id: int | None = None
    chat_title: str = ""
    bot_mentioned: bool = False
    has_media: bool = False
    media_type: str | None = None  # "photo" | "voice" | "video" | "document" | "audio" | "sticker"
    media_file_id: str | None = None
    caption: str = ""

    @property
    def effective_text(self) -> str:
        return self.text or self.caption


# ─── Thread bindings ───

class ThreadBindingStore:
    """Tracks Telegram topic thread bindings."""

    def __init__(self) -> None:
        self._bindings: dict[str, int] = {}  # chat:agent -> thread_id
        self._reverse: dict[str, str] = {}   # chat:thread -> agent_id

    def bind(self, chat_id: int, thread_id: int, agent_id: str) -> None:
        key = f"{chat_id}:{agent_id}"
        self._bindings[key] = thread_id
        self._reverse[f"{chat_id}:{thread_id}"] = agent_id

    def get_thread(self, chat_id: int, agent_id: str) -> int | None:
        return self._bindings.get(f"{chat_id}:{agent_id}")

    def get_agent(self, chat_id: int, thread_id: int) -> str | None:
        return self._reverse.get(f"{chat_id}:{thread_id}")

    def unbind(self, chat_id: int, agent_id: str) -> None:
        key = f"{chat_id}:{agent_id}"
        thread = self._bindings.pop(key, None)
        if thread is not None:
            self._reverse.pop(f"{chat_id}:{thread}", None)


# ─── Native commands ───

TELEGRAM_NATIVE_COMMANDS = [
    {"command": "start", "description": "Start the bot"},
    {"command": "help", "description": "Show help"},
    {"command": "new", "description": "Start a new session"},
    {"command": "model", "description": "Switch model"},
    {"command": "status", "description": "Show bot status"},
    {"command": "agents", "description": "List agents"},
    {"command": "lang", "description": "Set language"},
    {"command": "stop", "description": "Stop responding"},
]


async def handle_native_command(
    command: str,
    context: TelegramMessageContext,
    *,
    config: dict[str, Any] | None = None,
) -> str | None:
    """Handle a Telegram /command."""
    if command == "start":
        return "👋 Welcome! I'm your AI assistant. Send me a message to get started!"
    elif command == "help":
        lines = ["Available commands:"]
        for cmd in TELEGRAM_NATIVE_COMMANDS:
            lines.append(f"/{cmd['command']} — {cmd['description']}")
        return "\n".join(lines)
    elif command == "new":
        return "🔄 New session started. Your conversation history has been cleared."
    elif command == "model":
        return "Current model: claude-sonnet-4-20250514\nUse /model <name> to switch."
    elif command == "status":
        return f"✅ Bot is running\n📊 Chat ID: {context.chat_id}"
    elif command == "agents":
        return "🤖 Default agent is active.\nUse /agents to list all configured agents."
    elif command == "stop":
        return "⏹ Stopped. Send /start to resume."
    return None


# ─── Message dispatch ───

@dataclass
class DispatchDecision:
    should_reply: bool = True
    reason: str = ""
    agent_id: str = ""
    is_command: bool = False
    command: str = ""
    command_args: str = ""


def dispatch_message(
    context: TelegramMessageContext,
    *,
    allowed_chats: list[int] | None = None,
    admin_users: list[int] | None = None,
) -> DispatchDecision:
    """Decide how to handle an incoming Telegram message."""
    decision = DispatchDecision()

    # Filter by allowed chats
    if allowed_chats and context.chat_id not in allowed_chats:
        decision.should_reply = False
        decision.reason = "Chat not in allowlist"
        return decision

    text = context.effective_text.strip()

    # Check for command
    if text.startswith("/"):
        parts = text[1:].split(None, 1)
        cmd = parts[0].split("@")[0].lower()  # /cmd@botname -> cmd
        decision.is_command = True
        decision.command = cmd
        decision.command_args = parts[1] if len(parts) > 1 else ""
        return decision

    # Private chat — always reply
    if context.is_private:
        return decision

    # Group — only reply if mentioned
    if context.is_group or context.is_supergroup:
        if not context.bot_mentioned and not context.is_reply:
            decision.should_reply = False
            decision.reason = "Not mentioned in group"

    return decision


# ─── Delivery ───

async def deliver_telegram_reply(
    adapter: Any,
    *,
    chat_id: int,
    text: str,
    reply_to: int | None = None,
    parse_mode: str = "MarkdownV2",
    keyboard: dict[str, Any] | None = None,
) -> list[int]:
    """Deliver a reply via Telegram, splitting if needed."""
    from . import split_telegram_message, escape_telegram_markdown

    # Apply markdown escaping for MarkdownV2
    if parse_mode == "MarkdownV2":
        # Preserve code blocks, escape rest
        parts = text.split("```")
        escaped_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                escaped_parts.append(escape_telegram_markdown(part))
            else:
                escaped_parts.append(part)
        text = "```".join(escaped_parts)

    chunks = split_telegram_message(text)
    sent_ids = []

    for i, chunk in enumerate(chunks):
        msg_id = await adapter.send_message(
            chat_id, chunk,
            reply_to=reply_to if i == 0 else None,
            parse_mode=parse_mode,
            keyboard=keyboard if i == len(chunks) - 1 else None,
        )
        if isinstance(msg_id, list):
            sent_ids.extend(msg_id)
        else:
            sent_ids.append(msg_id)

    return sent_ids


# ─── Lane delivery (text deliverer) ───

@dataclass
class DeliveryTarget:
    chat_id: int = 0
    thread_id: int | None = None
    reply_to_id: int | None = None
    agent_id: str = ""


class TextDeliverer:
    """Handles text delivery through Telegram lanes."""

    def __init__(self, adapter: Any):
        self._adapter = adapter
        self._pending: list[tuple[DeliveryTarget, str]] = []

    async def deliver(self, target: DeliveryTarget, text: str) -> list[int]:
        return await deliver_telegram_reply(
            self._adapter,
            chat_id=target.chat_id,
            text=text,
            reply_to=target.reply_to_id,
        )

    def queue(self, target: DeliveryTarget, text: str) -> None:
        self._pending.append((target, text))

    async def flush(self) -> list[int]:
        all_ids = []
        for target, text in self._pending:
            ids = await self.deliver(target, text)
            all_ids.extend(ids)
        self._pending.clear()
        return all_ids

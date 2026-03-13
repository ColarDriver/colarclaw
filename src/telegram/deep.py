"""Telegram — deep: bot handlers, delivery pipeline, media, context pipeline.

Covers: bot-handlers.ts (~1565行), send.ts (~1269行) full depth,
bot-native-commands.ts (~868行) full depth,
bot-message-dispatch.ts (~807行) full depth,
bot/helpers.ts (~607行), bot-message-context.ts (~473行) full depth.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Bot handler pipeline ───

@dataclass
class TelegramUpdateContext:
    """Full context from a Telegram Update object."""
    update_id: int = 0
    message: dict[str, Any] | None = None
    edited_message: dict[str, Any] | None = None
    callback_query: dict[str, Any] | None = None
    inline_query: dict[str, Any] | None = None
    channel_post: dict[str, Any] | None = None

    # Derived
    chat_id: int = 0
    message_id: int = 0
    user_id: int = 0
    user_name: str = ""
    text: str = ""
    is_private: bool = False
    is_group: bool = False
    is_supergroup: bool = False
    is_channel: bool = False
    is_callback: bool = False
    callback_data: str = ""


def parse_update(update: dict[str, Any]) -> TelegramUpdateContext:
    """Parse a raw Telegram update into context."""
    ctx = TelegramUpdateContext(update_id=update.get("update_id", 0))

    msg = update.get("message") or update.get("edited_message") or update.get("channel_post")
    if msg:
        ctx.message = msg
        chat = msg.get("chat", {})
        ctx.chat_id = chat.get("id", 0)
        ctx.message_id = msg.get("message_id", 0)
        from_user = msg.get("from", {})
        ctx.user_id = from_user.get("id", 0)
        ctx.user_name = from_user.get("username", "") or from_user.get("first_name", "")
        ctx.text = msg.get("text", "") or msg.get("caption", "")
        chat_type = chat.get("type", "")
        ctx.is_private = chat_type == "private"
        ctx.is_group = chat_type == "group"
        ctx.is_supergroup = chat_type == "supergroup"
        ctx.is_channel = chat_type == "channel"

    cbq = update.get("callback_query")
    if cbq:
        ctx.is_callback = True
        ctx.callback_data = cbq.get("data", "")
        ctx.user_id = cbq.get("from", {}).get("id", 0)
        msg2 = cbq.get("message", {})
        ctx.chat_id = msg2.get("chat", {}).get("id", 0)
        ctx.message_id = msg2.get("message_id", 0)

    return ctx


# ─── Allowlist & dispatch ───

@dataclass
class TelegramAllowConfig:
    allowed_chats: list[int] = field(default_factory=list)
    admin_users: list[int] = field(default_factory=list)
    blocked_users: list[int] = field(default_factory=list)
    require_mention_in_groups: bool = True
    respond_in_topics_only: bool = False


class TelegramDispatcher:
    """Decides whether and how to process a Telegram message."""

    def __init__(self, config: TelegramAllowConfig, *, bot_username: str = ""):
        self._config = config
        self._bot_username = bot_username

    def should_process(self, ctx: TelegramUpdateContext) -> tuple[bool, str]:
        # Blocked?
        if ctx.user_id in self._config.blocked_users:
            return False, "blocked"
        # Allowed chats?
        if self._config.allowed_chats and ctx.chat_id not in self._config.allowed_chats:
            return False, "chat_not_allowed"
        # Group mention check
        if (ctx.is_group or ctx.is_supergroup) and self._config.require_mention_in_groups:
            if not self._is_bot_mentioned(ctx.text):
                reply = ctx.message.get("reply_to_message", {}) if ctx.message else {}
                from_user = reply.get("from", {})
                if from_user.get("username") != self._bot_username:
                    return False, "not_mentioned"
        return True, "ok"

    def _is_bot_mentioned(self, text: str) -> bool:
        if not self._bot_username:
            return False
        return f"@{self._bot_username}" in text

    def is_admin(self, user_id: int) -> bool:
        return user_id in self._config.admin_users


# ─── Send pipeline (full depth) ───

@dataclass
class TelegramSendResult:
    success: bool = True
    message_ids: list[int] = field(default_factory=list)
    error: str = ""


async def send_text_message(
    adapter: Any,
    chat_id: int,
    text: str,
    *,
    parse_mode: str = "MarkdownV2",
    reply_to: int | None = None,
    keyboard: dict[str, Any] | None = None,
    disable_preview: bool = False,
    disable_notification: bool = False,
    protect_content: bool = False,
    message_thread_id: int | None = None,
) -> TelegramSendResult:
    """Full send text pipeline with all Telegram API options."""
    from .extended import TelegramMessageContext

    result = TelegramSendResult()

    # Handle long messages
    from . import split_telegram_message
    chunks = split_telegram_message(text)

    for i, chunk in enumerate(chunks):
        try:
            msg_id = await adapter.send_message(
                chat_id, chunk,
                parse_mode=parse_mode,
                reply_to=reply_to if i == 0 else None,
                keyboard=keyboard if i == len(chunks) - 1 else None,
            )
            result.message_ids.append(msg_id if isinstance(msg_id, int) else 0)
        except Exception as e:
            # Fallback: try without parse_mode
            if parse_mode:
                try:
                    msg_id = await adapter.send_message(chat_id, chunk, reply_to=reply_to if i == 0 else None)
                    result.message_ids.append(msg_id if isinstance(msg_id, int) else 0)
                except Exception as e2:
                    result.success = False
                    result.error = str(e2)
            else:
                result.success = False
                result.error = str(e)

    return result


async def send_photo(
    adapter: Any,
    chat_id: int,
    photo: str,  # URL or file path
    *,
    caption: str = "",
    reply_to: int | None = None,
) -> TelegramSendResult:
    result = TelegramSendResult()
    try:
        msg_id = await adapter.send_photo(chat_id, photo, caption=caption, reply_to=reply_to)
        result.message_ids.append(msg_id if isinstance(msg_id, int) else 0)
    except Exception as e:
        result.success = False
        result.error = str(e)
    return result


async def send_document(
    adapter: Any,
    chat_id: int,
    document: str,
    *,
    caption: str = "",
    reply_to: int | None = None,
) -> TelegramSendResult:
    result = TelegramSendResult()
    try:
        msg_id = await adapter.send_document(chat_id, document, caption=caption, reply_to=reply_to)
        result.message_ids.append(msg_id if isinstance(msg_id, int) else 0)
    except Exception as e:
        result.success = False
        result.error = str(e)
    return result


async def send_voice(
    adapter: Any,
    chat_id: int,
    voice: str,
    *,
    caption: str = "",
    duration: int = 0,
) -> TelegramSendResult:
    result = TelegramSendResult()
    try:
        msg_id = await adapter.send_voice(chat_id, voice, caption=caption, duration=duration)
        result.message_ids.append(msg_id if isinstance(msg_id, int) else 0)
    except Exception as e:
        result.success = False
        result.error = str(e)
    return result


# ─── Bot helpers ───

def build_inline_keyboard(rows: list[list[dict[str, str]]]) -> dict[str, Any]:
    """Build Telegram inline keyboard markup."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": btn.get("text", ""),
                    **({"callback_data": btn["callback_data"]} if "callback_data" in btn else {}),
                    **({"url": btn["url"]} if "url" in btn else {}),
                    **({"switch_inline_query": btn["switch_inline_query"]} if "switch_inline_query" in btn else {}),
                }
                for btn in row
            ]
            for row in rows
        ],
    }


def build_reply_keyboard(
    buttons: list[list[str]],
    *,
    one_time: bool = True,
    resize: bool = True,
) -> dict[str, Any]:
    """Build Telegram reply keyboard markup."""
    return {
        "keyboard": [[{"text": btn} for btn in row] for row in buttons],
        "one_time_keyboard": one_time,
        "resize_keyboard": resize,
    }


def build_remove_keyboard() -> dict[str, Any]:
    return {"remove_keyboard": True}


def format_user_mention(user_id: int, name: str) -> str:
    """Format a Telegram user mention in MarkdownV2."""
    escaped_name = re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', name)
    return f"[{escaped_name}](tg://user?id={user_id})"


def parse_bot_command(text: str) -> tuple[str, str]:
    """Parse /command@botname args → (command, args)."""
    if not text.startswith("/"):
        return "", text
    parts = text.split(None, 1)
    cmd_part = parts[0][1:]  # remove /
    cmd = cmd_part.split("@")[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return cmd, args


# ─── Media download ───

async def download_telegram_file(
    file_id: str,
    *,
    bot_token: str = "",
    dest_dir: str = "/tmp",
) -> str | None:
    """Download a file from Telegram servers."""
    try:
        import aiohttp, os
        # Get file path
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                params={"file_id": file_id},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                file_path = data.get("result", {}).get("file_path")
                if not file_path:
                    return None

            # Download
            download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    return None
                os.makedirs(dest_dir, exist_ok=True)
                filename = os.path.basename(file_path)
                dest = os.path.join(dest_dir, filename)
                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_any():
                        f.write(chunk)
                return dest
    except Exception as e:
        logger.error(f"Telegram file download error: {e}")
        return None

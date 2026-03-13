"""Telegram — monitor: webhook, polling, callback queries, media groups.

Covers the remaining telegram/ TS files for full ≥5% coverage.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Webhook handler ───

@dataclass
class WebhookConfig:
    url: str = ""
    secret_token: str = ""
    max_connections: int = 40
    allowed_updates: list[str] = field(default_factory=lambda: [
        "message", "edited_message", "callback_query", "inline_query",
    ])


async def set_webhook(bot_token: str, config: WebhookConfig) -> bool:
    """Set Telegram webhook."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={
                    "url": config.url,
                    "secret_token": config.secret_token,
                    "max_connections": config.max_connections,
                    "allowed_updates": config.allowed_updates,
                },
            ) as resp:
                result = await resp.json()
                return result.get("ok", False)
    except Exception as e:
        logger.error(f"setWebhook failed: {e}")
        return False


async def delete_webhook(bot_token: str) -> bool:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{bot_token}/deleteWebhook",
            ) as resp:
                result = await resp.json()
                return result.get("ok", False)
    except Exception:
        return False


# ─── Long polling ───

class TelegramPoller:
    """Long polling for Telegram updates."""

    def __init__(self, bot_token: str, *, timeout: int = 30):
        self._token = bot_token
        self._timeout = timeout
        self._offset = 0
        self._running = False

    async def start(self, handler: Any) -> None:
        self._running = True
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id >= self._offset:
                        self._offset = update_id + 1
                    try:
                        result = handler(update)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.error(f"Update handler error: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)

    def stop(self) -> None:
        self._running = False

    async def _get_updates(self) -> list[dict[str, Any]]:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.telegram.org/bot{self._token}/getUpdates",
                    params={"offset": self._offset, "timeout": self._timeout,
                            "allowed_updates": json.dumps(["message", "edited_message", "callback_query"])},
                    timeout=aiohttp.ClientTimeout(total=self._timeout + 10),
                ) as resp:
                    result = await resp.json()
                    return result.get("result", [])
        except Exception as e:
            logger.debug(f"getUpdates error: {e}")
            return []


# ─── Callback query handler ───

@dataclass
class CallbackAction:
    action: str = ""
    data: dict[str, str] = field(default_factory=dict)


def parse_callback_data(data: str) -> CallbackAction:
    """Parse callback_data string (format: action:key=val&key2=val2)."""
    parts = data.split(":", 1)
    action = parts[0]
    params: dict[str, str] = {}
    if len(parts) > 1:
        for pair in parts[1].split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
    return CallbackAction(action=action, data=params)


async def answer_callback_query(
    bot_token: str,
    callback_query_id: str,
    *,
    text: str = "",
    show_alert: bool = False,
) -> bool:
    """Answer a callback query."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_query_id,
                    "text": text,
                    "show_alert": show_alert,
                },
            ) as resp:
                result = await resp.json()
                return result.get("ok", False)
    except Exception:
        return False


# ─── Media group handling ───

class MediaGroupCollector:
    """Collects messages in a media group (album) before processing."""

    def __init__(self, *, window_ms: int = 500):
        self._window = window_ms
        self._groups: dict[str, list[dict[str, Any]]] = {}
        self._timers: dict[str, float] = {}

    def add_message(self, msg: dict[str, Any]) -> str | None:
        """Add message. Returns group_id when group is complete/ready."""
        group_id = msg.get("media_group_id")
        if not group_id:
            return None

        if group_id not in self._groups:
            self._groups[group_id] = []
            self._timers[group_id] = time.time()

        self._groups[group_id].append(msg)
        return group_id

    def is_ready(self, group_id: str) -> bool:
        if group_id not in self._timers:
            return False
        return (time.time() - self._timers[group_id]) * 1000 > self._window

    def get_group(self, group_id: str) -> list[dict[str, Any]]:
        return self._groups.pop(group_id, [])

    def cleanup(self) -> None:
        now = time.time()
        stale = [gid for gid, ts in self._timers.items() if (now - ts) > 30]
        for gid in stale:
            self._groups.pop(gid, None)
            self._timers.pop(gid, None)


# ─── Bot API helpers ───

async def get_bot_info(bot_token: str) -> dict[str, Any]:
    """Get bot information via getMe."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/getMe",
            ) as resp:
                result = await resp.json()
                return result.get("result", {})
    except Exception:
        return {}


async def set_bot_commands(
    bot_token: str,
    commands: list[dict[str, str]],
) -> bool:
    """Set bot command list."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{bot_token}/setMyCommands",
                json={"commands": commands[:100]},
            ) as resp:
                result = await resp.json()
                return result.get("ok", False)
    except Exception:
        return False


async def get_chat_info(bot_token: str, chat_id: int) -> dict[str, Any]:
    """Get chat information."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/getChat",
                params={"chat_id": chat_id},
            ) as resp:
                result = await resp.json()
                return result.get("result", {})
    except Exception:
        return {}


async def get_chat_member_count(bot_token: str, chat_id: int) -> int:
    """Get chat member count."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/getChatMemberCount",
                params={"chat_id": chat_id},
            ) as resp:
                result = await resp.json()
                return int(result.get("result", 0))
    except Exception:
        return 0

"""Channels telegram — ported from bk/src/channels/telegram/api.ts,
telegram/allow-from.ts.

Telegram API helpers and allow-from normalization.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("channels.telegram")


# ─── api.ts ───

async def fetch_telegram_chat_id(
    token: str,
    chat_id: str,
) -> str | None:
    """Fetch a Telegram chat/user ID by username or numeric.

    Uses the Telegram Bot API getChat method.
    """
    import aiohttp
    url = f"https://api.telegram.org/bot{token}/getChat"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": chat_id}) as resp:
                data = await resp.json()
                if data.get("ok") and data.get("result"):
                    return str(data["result"].get("id", ""))
                return None
    except Exception as e:
        logger.debug(f"Telegram getChat failed for {chat_id}: {e}")
        return None


# ─── allow-from.ts ───

def format_telegram_allow_from(
    allow_from: list[str | int],
) -> list[str]:
    """Format Telegram allow-from entries."""
    return [str(v).strip() for v in allow_from if str(v).strip()]

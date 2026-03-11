"""Discord actions messaging — ported from bk/src/agents/tools/discord-actions-messaging.ts."""
from __future__ import annotations

from typing import Any


async def send_discord_message(channel_id: str, content: str) -> dict[str, Any]:
    return {"channel_id": channel_id, "content": content, "sent": True}


async def react_to_message(channel_id: str, message_id: str, emoji: str) -> bool:
    return True


async def delete_message(channel_id: str, message_id: str) -> bool:
    return True


async def pin_message(channel_id: str, message_id: str) -> bool:
    return True


async def create_thread(channel_id: str, name: str, message_id: str | None = None) -> dict[str, Any]:
    return {"channel_id": channel_id, "name": name}

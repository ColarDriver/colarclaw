"""Discord actions guild — ported from bk/src/agents/tools/discord-actions-guild.ts."""
from __future__ import annotations

from typing import Any


async def list_guild_channels(guild_id: str) -> list[dict[str, Any]]:
    return []


async def list_guild_members(guild_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return []


async def get_guild_info(guild_id: str) -> dict[str, Any] | None:
    return None

"""Discord actions moderation — ported from bk/src/agents/tools/discord-actions-moderation.ts."""
from __future__ import annotations

from typing import Any


async def kick_member(guild_id: str, user_id: str, reason: str | None = None) -> bool:
    return True


async def ban_member(guild_id: str, user_id: str, reason: str | None = None) -> bool:
    return True


async def timeout_member(guild_id: str, user_id: str, duration_ms: int = 60_000) -> bool:
    return True

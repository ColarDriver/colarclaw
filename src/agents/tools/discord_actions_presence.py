"""Discord actions presence — ported from bk/src/agents/tools/discord-actions-presence.ts."""
from __future__ import annotations

from typing import Any, Literal

PresenceStatus = Literal["online", "idle", "dnd", "invisible"]


async def set_presence(status: PresenceStatus, activity: str | None = None) -> bool:
    return True


async def get_presence() -> dict[str, Any]:
    return {"status": "online", "activity": None}

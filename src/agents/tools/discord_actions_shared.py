"""Discord actions shared — ported from bk/src/agents/tools/discord-actions-shared.ts."""
from __future__ import annotations

from typing import Any


def format_discord_channel_mention(channel_id: str) -> str:
    return f"<#{channel_id}>"


def format_discord_user_mention(user_id: str) -> str:
    return f"<@{user_id}>"


def parse_discord_mention(mention: str) -> str | None:
    if mention.startswith("<@") and mention.endswith(">"):
        return mention[2:-1].lstrip("!")
    if mention.startswith("<#") and mention.endswith(">"):
        return mention[2:-1]
    return None

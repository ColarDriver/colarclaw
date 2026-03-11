"""Discord actions moderation shared — ported from bk/src/agents/tools/discord-actions-moderation-shared.ts."""
from __future__ import annotations

from typing import Any, Literal

ModerationAction = Literal["kick", "ban", "timeout", "mute", "unmute"]


def format_moderation_log(
    action: ModerationAction, user_id: str, moderator_id: str | None = None, reason: str | None = None,
) -> str:
    parts = [f"Action: {action}", f"User: {user_id}"]
    if moderator_id:
        parts.append(f"By: {moderator_id}")
    if reason:
        parts.append(f"Reason: {reason}")
    return " | ".join(parts)

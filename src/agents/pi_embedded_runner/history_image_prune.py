"""Pi embedded runner history image prune — ported from bk/src/agents/pi-embedded-runner/run/history-image-prune.ts."""
from __future__ import annotations

from typing import Any


def prune_history_images(
    messages: list[dict[str, Any]],
    keep_last_n: int = 3,
) -> list[dict[str, Any]]:
    """Remove old image content from history to save tokens."""
    if len(messages) <= keep_last_n:
        return messages

    result = []
    for i, msg in enumerate(messages):
        if i >= len(messages) - keep_last_n:
            result.append(msg)
            continue
        content = msg.get("content")
        if isinstance(content, list):
            filtered = [
                block for block in content
                if not (isinstance(block, dict) and block.get("type") in ("image_url", "image"))
            ]
            if not filtered:
                filtered = [{"type": "text", "text": "(image removed for context)"}]
            result.append({**msg, "content": filtered})
        else:
            result.append(msg)
    return result

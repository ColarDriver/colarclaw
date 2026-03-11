"""Content block helpers — ported from bk/src/agents/content-blocks.ts."""
from __future__ import annotations
from typing import Any

def collect_text_content_blocks(content: Any) -> list[str]:
    if not isinstance(content, list):
        return []
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return parts

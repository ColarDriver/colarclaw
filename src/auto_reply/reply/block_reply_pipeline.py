"""Reply block pipeline — ported from bk/src/auto-reply/reply/block-reply-pipeline.ts + block-reply-coalescer.ts + block-streaming.ts."""
from __future__ import annotations

from typing import Any, Callable


class BlockReplyCoalescer:
    """Coalesces streaming text blocks into coherent reply segments."""

    def __init__(self, max_delay_ms: int = 500):
        self._buffer: list[str] = []
        self._max_delay_ms = max_delay_ms

    def append(self, text: str) -> None:
        self._buffer.append(text)

    def flush(self) -> str:
        result = "".join(self._buffer)
        self._buffer.clear()
        return result

    @property
    def has_content(self) -> bool:
        return len(self._buffer) > 0


async def process_block_reply_pipeline(
    blocks: list[dict[str, Any]],
    on_block: Callable[[dict[str, Any]], Any] | None = None,
) -> list[dict[str, Any]]:
    results = []
    for block in blocks:
        if on_block:
            result = on_block(block)
            if hasattr(result, "__await__"):
                result = await result
            if result is not None:
                results.append(result)
        else:
            results.append(block)
    return results


def coalesce_text_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not blocks:
        return []
    coalesced: list[dict[str, Any]] = []
    current_text: list[str] = []

    for block in blocks:
        if block.get("type") == "text":
            current_text.append(block.get("content", ""))
        else:
            if current_text:
                coalesced.append({"type": "text", "content": "".join(current_text)})
                current_text.clear()
            coalesced.append(block)

    if current_text:
        coalesced.append({"type": "text", "content": "".join(current_text)})
    return coalesced

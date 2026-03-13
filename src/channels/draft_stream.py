"""Channels draft stream — ported from bk/src/channels/draft-stream-controls.ts,
draft-stream-loop.ts.

Draft stream controls for managing block streaming (coalesced chunk output).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("channels.draft_stream")


@dataclass
class DraftStreamCoalesceConfig:
    min_chars: int = 1500
    idle_ms: int = 1000


@dataclass
class DraftStreamState:
    buffer: str = ""
    last_flush_ms: float = 0.0
    chunk_count: int = 0
    total_chars: int = 0


class DraftStreamController:
    """Controls block streaming with coalesced chunks.

    Accumulates text until either min_chars is reached or idle_ms
    has passed since the last flush, then emits a coalesced chunk.
    """

    def __init__(
        self,
        on_flush: Callable[[str, int], Any],
        config: DraftStreamCoalesceConfig | None = None,
    ):
        cfg = config or DraftStreamCoalesceConfig()
        self._on_flush = on_flush
        self._min_chars = max(1, cfg.min_chars)
        self._idle_ms = max(100, cfg.idle_ms)
        self._state = DraftStreamState()
        self._idle_task: asyncio.Task | None = None
        self._closed = False

    def append(self, text: str) -> None:
        """Append text to the buffer, flushing if threshold reached."""
        if self._closed or not text:
            return
        self._state.buffer += text
        self._state.total_chars += len(text)
        self._cancel_idle()

        if len(self._state.buffer) >= self._min_chars:
            self._flush_now()
        else:
            self._schedule_idle_flush()

    def _flush_now(self) -> None:
        if not self._state.buffer:
            return
        chunk = self._state.buffer
        self._state.buffer = ""
        self._state.chunk_count += 1
        self._state.last_flush_ms = time.time() * 1000
        self._cancel_idle()
        try:
            self._on_flush(chunk, self._state.chunk_count)
        except Exception as e:
            logger.warning(f"draft stream flush error: {e}")

    def _schedule_idle_flush(self) -> None:
        self._cancel_idle()

        async def _idle():
            await asyncio.sleep(self._idle_ms / 1000.0)
            if not self._closed and self._state.buffer:
                self._flush_now()

        try:
            self._idle_task = asyncio.create_task(_idle())
        except RuntimeError:
            # No event loop
            pass

    def _cancel_idle(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    def flush(self) -> None:
        """Force flush any remaining buffer."""
        self._cancel_idle()
        self._flush_now()

    def close(self) -> None:
        """Close the controller, flushing remaining content."""
        self._closed = True
        self._cancel_idle()
        self._flush_now()

    @property
    def stats(self) -> dict[str, int]:
        return {
            "chunkCount": self._state.chunk_count,
            "totalChars": self._state.total_chars,
            "bufferLen": len(self._state.buffer),
        }

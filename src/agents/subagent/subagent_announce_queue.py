"""Subagent announce queue — ported from bk/src/agents/subagent-announce-queue.ts."""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Callable


class SubagentAnnounceQueue:
    """Queues subagent announcements for ordered dispatch."""

    def __init__(self, dispatcher: Callable[[str, str | None], Any] | None = None):
        self._queue: deque[tuple[str, str | None]] = deque()
        self._dispatcher = dispatcher
        self._processing = False

    def enqueue(self, message: str, channel: str | None = None) -> None:
        self._queue.append((message, channel))

    async def process(self) -> int:
        if self._processing or not self._dispatcher:
            return 0
        self._processing = True
        count = 0
        try:
            while self._queue:
                msg, ch = self._queue.popleft()
                try:
                    await self._dispatcher(msg, ch)
                    count += 1
                except Exception:
                    pass
        finally:
            self._processing = False
        return count

    def clear(self) -> None:
        self._queue.clear()

    @property
    def pending_count(self) -> int:
        return len(self._queue)

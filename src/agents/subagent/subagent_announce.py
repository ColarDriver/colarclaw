"""Subagent announce — ported from bk/src/agents/subagent-announce*.ts.

Handles sub-agent completion announcements, dispatch, and queuing.
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("openclaw.agents.subagent_announce")

@dataclass
class AnnounceItem:
    announce_id: str
    session_key: str
    child_session_key: str
    child_run_id: str
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)

class AnnounceQueue:
    def __init__(self, max_size: int = 1000):
        self._queue: list[AnnounceItem] = []
        self._max_size = max_size
        self._processed: set[str] = set()

    def enqueue(self, item: AnnounceItem) -> bool:
        if item.announce_id in self._processed:
            log.debug("Skipping duplicate announce %s", item.announce_id)
            return False
        if len(self._queue) >= self._max_size:
            self._queue = self._queue[len(self._queue) // 2:]
        self._queue.append(item)
        return True

    def dequeue(self) -> AnnounceItem | None:
        if not self._queue:
            return None
        item = self._queue.pop(0)
        self._processed.add(item.announce_id)
        return item

    def size(self) -> int:
        return len(self._queue)

    def clear(self) -> None:
        self._queue.clear()

class AnnounceDispatcher:
    def __init__(self):
        self._handlers: list[Callable[[AnnounceItem], Any]] = []

    def on_announce(self, handler: Callable[[AnnounceItem], Any]) -> None:
        self._handlers.append(handler)

    async def dispatch(self, item: AnnounceItem) -> None:
        for handler in self._handlers:
            try:
                result = handler(item)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.error("Announce handler error: %s", e)

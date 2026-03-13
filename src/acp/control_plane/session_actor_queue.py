"""ACP control plane session actor queue — ported from bk/src/acp/control-plane/session-actor-queue.ts."""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Callable, Coroutine


class SessionActorQueue:
    """Serializes async operations per session to prevent race conditions."""

    def __init__(self):
        self._queues: dict[str, deque[Callable[[], Coroutine]]] = {}
        self._running: set[str] = set()

    async def enqueue(self, session_key: str, task: Callable[[], Coroutine]) -> Any:
        if session_key not in self._queues:
            self._queues[session_key] = deque()

        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def run() -> None:
            try:
                result = await task()
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

        self._queues[session_key].append(run)
        await self._process(session_key)
        return await future

    async def _process(self, session_key: str) -> None:
        if session_key in self._running:
            return
        self._running.add(session_key)
        try:
            while self._queues.get(session_key):
                task = self._queues[session_key].popleft()
                await task()
        finally:
            self._running.discard(session_key)
            if not self._queues.get(session_key):
                self._queues.pop(session_key, None)

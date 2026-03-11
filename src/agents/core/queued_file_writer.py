"""Queued file writer — ported from bk/src/agents/queued-file-writer.ts.

Async file writer that queues writes and executes them serially
to prevent race conditions on file I/O.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

log = logging.getLogger("openclaw.agents.queued_file_writer")


class QueuedFileWriter:
    """Queues write operations and executes them serially."""

    def __init__(self, max_queue_size: int = 100):
        self._queue: asyncio.Queue[tuple[str, str, asyncio.Future[None]]] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background write loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop the background write loop and flush pending writes."""
        self._running = False
        if self._task:
            # Signal shutdown
            dummy_future: asyncio.Future[None] = asyncio.get_event_loop().create_future()
            dummy_future.set_result(None)
            await self._queue.put(("", "", dummy_future))
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None

    async def write(self, file_path: str, content: str) -> None:
        """Queue a file write and wait for it to complete."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[None] = loop.create_future()
        await self._queue.put((file_path, content, future))
        await future

    async def write_fire_and_forget(self, file_path: str, content: str) -> None:
        """Queue a file write without waiting for completion."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[None] = loop.create_future()
        future.set_result(None)
        try:
            self._queue.put_nowait((file_path, content, future))
        except asyncio.QueueFull:
            log.warning("Write queue full, dropping write for %s", file_path)

    async def _process_loop(self) -> None:
        while self._running or not self._queue.empty():
            try:
                file_path, content, future = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            if not file_path:
                continue

            try:
                await self._write_file(file_path, content)
                if not future.done():
                    future.set_result(None)
            except Exception as exc:
                log.error("Failed to write %s: %s", file_path, exc)
                if not future.done():
                    future.set_exception(exc)

    @staticmethod
    async def _write_file(file_path: str, content: str) -> None:
        """Write content to file, creating directories as needed."""
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Use sync write in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_write_file, file_path, content)

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()


def _sync_write_file(path: str, content: str) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp_path, path)

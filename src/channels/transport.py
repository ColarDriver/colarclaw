"""Channels transport — ported from bk/src/channels/transport/stall-watchdog.ts.

Transport-level stall watchdog: detects stalled channel connections
and triggers recovery actions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

logger = logging.getLogger("channels.transport")

DEFAULT_STALL_TIMEOUT_MS = 30_000
DEFAULT_HEALTH_CHECK_INTERVAL_MS = 10_000


class StallWatchdog:
    """Detects stalled transport connections via periodic health checks."""

    def __init__(
        self,
        label: str,
        stall_timeout_ms: int = DEFAULT_STALL_TIMEOUT_MS,
        health_check_interval_ms: int = DEFAULT_HEALTH_CHECK_INTERVAL_MS,
        on_stall: Callable[[], None] | None = None,
    ):
        self._label = label
        self._stall_timeout_ms = stall_timeout_ms
        self._health_check_interval_ms = health_check_interval_ms
        self._on_stall = on_stall
        self._last_activity_ms = time.time() * 1000
        self._task: asyncio.Task | None = None
        self._running = False

    def mark_activity(self) -> None:
        """Mark the transport as active (received data/heartbeat)."""
        self._last_activity_ms = time.time() * 1000

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._last_activity_ms = time.time() * 1000
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._health_check_interval_ms / 1000.0)
                if not self._running:
                    break
                now = time.time() * 1000
                elapsed = now - self._last_activity_ms
                if elapsed > self._stall_timeout_ms:
                    logger.warning(
                        f"[{self._label}] transport stall detected "
                        f"(no activity for {elapsed:.0f}ms)"
                    )
                    if self._on_stall:
                        self._on_stall()
                    self._last_activity_ms = now
        except asyncio.CancelledError:
            pass

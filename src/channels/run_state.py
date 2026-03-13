"""Channels run_state — ported from bk/src/channels/run-state-machine.ts.

Run state machine for tracking active agent runs, with heartbeat
publishing and lifecycle management.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("channels.run_state")

DEFAULT_RUN_ACTIVITY_HEARTBEAT_MS = 60_000


@dataclass
class RunStateStatusPatch:
    busy: bool = False
    active_runs: int = 0
    last_run_activity_at: float | None = None


class RunStateMachine:
    """Tracks active runs and publishes status updates with heartbeat."""

    def __init__(
        self,
        set_status: Callable[[RunStateStatusPatch], None] | None = None,
        heartbeat_ms: int = DEFAULT_RUN_ACTIVITY_HEARTBEAT_MS,
        now_fn: Callable[[], float] | None = None,
    ):
        self._set_status = set_status
        self._heartbeat_ms = heartbeat_ms
        self._now = now_fn or (lambda: time.time() * 1000)
        self._active_runs = 0
        self._heartbeat_task: asyncio.Task | None = None
        self._lifecycle_active = True

        # Reset inherited status
        if self._set_status:
            self._set_status(RunStateStatusPatch(active_runs=0, busy=False))

    def _publish(self) -> None:
        if not self._lifecycle_active or not self._set_status:
            return
        self._set_status(RunStateStatusPatch(
            active_runs=self._active_runs,
            busy=self._active_runs > 0,
            last_run_activity_at=self._now(),
        ))

    def _clear_heartbeat(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        self._heartbeat_task = None

    def _ensure_heartbeat(self) -> None:
        if self._heartbeat_task or self._active_runs <= 0 or not self._lifecycle_active:
            return

        async def _heartbeat():
            try:
                while self._lifecycle_active and self._active_runs > 0:
                    await asyncio.sleep(self._heartbeat_ms / 1000.0)
                    if self._lifecycle_active and self._active_runs > 0:
                        self._publish()
            except asyncio.CancelledError:
                pass

        self._heartbeat_task = asyncio.create_task(_heartbeat())

    def is_active(self) -> bool:
        return self._lifecycle_active

    def on_run_start(self) -> None:
        self._active_runs += 1
        self._publish()
        self._ensure_heartbeat()

    def on_run_end(self) -> None:
        self._active_runs = max(0, self._active_runs - 1)
        if self._active_runs <= 0:
            self._clear_heartbeat()
        self._publish()

    def deactivate(self) -> None:
        self._lifecycle_active = False
        self._clear_heartbeat()

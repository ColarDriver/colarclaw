"""Pi embedded runner runs — ported from bk/src/agents/pi-embedded-runner/runs.ts.

Manages multiple concurrent runs.
"""
from __future__ import annotations

import asyncio
from typing import Any

from .run_types import RunResult


class RunManager:
    """Manages active runs and their lifecycle."""

    def __init__(self, max_concurrent: int = 5):
        self._runs: dict[str, asyncio.Task[RunResult]] = {}
        self._results: dict[str, RunResult] = {}
        self._max_concurrent = max_concurrent

    @property
    def active_count(self) -> int:
        return len([t for t in self._runs.values() if not t.done()])

    def can_start(self) -> bool:
        return self.active_count < self._max_concurrent

    async def start(self, run_id: str, coro: Any) -> bool:
        if not self.can_start():
            return False
        task = asyncio.create_task(coro)
        self._runs[run_id] = task
        task.add_done_callback(lambda t: self._on_done(run_id, t))
        return True

    def _on_done(self, run_id: str, task: asyncio.Task[RunResult]) -> None:
        try:
            self._results[run_id] = task.result()
        except Exception as exc:
            self._results[run_id] = RunResult(status="failed", error=str(exc))

    def get_result(self, run_id: str) -> RunResult | None:
        return self._results.get(run_id)

    async def cancel(self, run_id: str) -> bool:
        task = self._runs.get(run_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def cancel_all(self) -> int:
        count = 0
        for run_id, task in self._runs.items():
            if not task.done():
                task.cancel()
                count += 1
        return count

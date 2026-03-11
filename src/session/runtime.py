from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import time


@dataclass
class RunState:
    run_id: str
    session_id: str
    started_at_ms: int
    idempotency_key: str | None
    status: str


class SessionRuntimeState:
    def __init__(self, *, idempotency_ttl_ms: int = 15 * 60 * 1000) -> None:
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._runs: dict[str, RunState] = {}
        self._session_runs: dict[str, set[str]] = {}
        self._idempotency_cache: dict[str, tuple[int, str]] = {}
        self._idempotency_order: deque[str] = deque()
        self._idempotency_ttl_ms = idempotency_ttl_ms

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def lock_for_session(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    def start_run(self, *, run_id: str, session_id: str, idempotency_key: str | None) -> None:
        state = RunState(
            run_id=run_id,
            session_id=session_id,
            started_at_ms=self._now_ms(),
            idempotency_key=idempotency_key,
            status="running",
        )
        self._runs[run_id] = state
        self._session_runs.setdefault(session_id, set()).add(run_id)
        if idempotency_key:
            cache_key = self._compose_idempotency_key(session_id=session_id, idempotency_key=idempotency_key)
            self._idempotency_cache[cache_key] = (state.started_at_ms, run_id)
            self._idempotency_order.append(cache_key)

    def finish_run(self, run_id: str, *, status: str = "completed") -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        state.status = status
        session_runs = self._session_runs.get(state.session_id)
        if session_runs:
            session_runs.discard(run_id)
            if not session_runs:
                self._session_runs.pop(state.session_id, None)

    def abort_run(self, run_id: str) -> bool:
        state = self._runs.get(run_id)
        if state is None:
            return False
        state.status = "aborted"
        self.finish_run(run_id, status="aborted")
        return True

    def active_runs_for_session(self, session_id: str) -> list[RunState]:
        run_ids = self._session_runs.get(session_id, set())
        return [self._runs[rid] for rid in run_ids if rid in self._runs]

    def find_run_by_idempotency(self, *, session_id: str, idempotency_key: str | None) -> str | None:
        if not idempotency_key:
            return None
        self._evict_old_idempotency()
        cache_key = self._compose_idempotency_key(session_id=session_id, idempotency_key=idempotency_key)
        item = self._idempotency_cache.get(cache_key)
        if not item:
            return None
        _, run_id = item
        return run_id

    def _compose_idempotency_key(self, *, session_id: str, idempotency_key: str) -> str:
        return f"{session_id}:{idempotency_key}"

    def _evict_old_idempotency(self) -> None:
        now = self._now_ms()
        while self._idempotency_order:
            key = self._idempotency_order[0]
            item = self._idempotency_cache.get(key)
            if item is None:
                self._idempotency_order.popleft()
                continue
            created_at_ms, _ = item
            if now - created_at_ms <= self._idempotency_ttl_ms:
                break
            self._idempotency_order.popleft()
            self._idempotency_cache.pop(key, None)

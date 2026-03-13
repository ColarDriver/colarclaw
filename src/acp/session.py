"""ACP session — ported from bk/src/acp/session.ts.

In-memory session store with TTL eviction and rate limiting.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Protocol

from .types import AcpSession

DEFAULT_MAX_SESSIONS = 5000
DEFAULT_IDLE_TTL_MS = 24 * 60 * 60 * 1000  # 24h


class AcpSessionStore(Protocol):
    def create_session(self, session_key: str, cwd: str, session_id: str | None = None) -> AcpSession: ...
    def has_session(self, session_id: str) -> bool: ...
    def get_session(self, session_id: str) -> AcpSession | None: ...
    def get_session_by_run_id(self, run_id: str) -> AcpSession | None: ...
    def set_active_run(self, session_id: str, run_id: str, abort_controller: Any) -> None: ...
    def clear_active_run(self, session_id: str) -> None: ...
    def cancel_active_run(self, session_id: str) -> bool: ...
    def clear_all_sessions_for_test(self) -> None: ...


class InMemorySessionStore:
    """In-memory ACP session store with idle TTL and capacity eviction."""

    def __init__(
        self,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        idle_ttl_ms: int = DEFAULT_IDLE_TTL_MS,
        now: Callable[[], float] | None = None,
    ):
        self._max_sessions = max(1, max_sessions)
        self._idle_ttl_ms = max(1000, idle_ttl_ms)
        self._now = now or (lambda: time.time() * 1000)
        self._sessions: dict[str, AcpSession] = {}
        self._run_id_to_session_id: dict[str, str] = {}

    def _touch(self, session: AcpSession) -> None:
        session.last_touched_at = self._now()

    def _remove(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        if session.active_run_id:
            self._run_id_to_session_id.pop(session.active_run_id, None)
        if session.abort_controller and hasattr(session.abort_controller, "abort"):
            session.abort_controller.abort()
        del self._sessions[session_id]
        return True

    def _reap_idle(self, now_ms: float) -> None:
        idle_before = now_ms - self._idle_ttl_ms
        to_remove = [
            sid for sid, s in self._sessions.items()
            if not s.active_run_id and not s.abort_controller and s.last_touched_at <= idle_before
        ]
        for sid in to_remove:
            self._remove(sid)

    def _evict_oldest_idle(self) -> bool:
        oldest_id: str | None = None
        oldest_ts = float("inf")
        for sid, s in self._sessions.items():
            if s.active_run_id or s.abort_controller:
                continue
            if s.last_touched_at < oldest_ts:
                oldest_ts = s.last_touched_at
                oldest_id = sid
        return self._remove(oldest_id) if oldest_id else False

    def create_session(self, session_key: str, cwd: str, session_id: str | None = None) -> AcpSession:
        now_ms = self._now()
        sid = session_id or str(uuid.uuid4())
        existing = self._sessions.get(sid)
        if existing:
            existing.session_key = session_key
            existing.cwd = cwd
            self._touch(existing)
            return existing
        self._reap_idle(now_ms)
        if len(self._sessions) >= self._max_sessions and not self._evict_oldest_idle():
            raise RuntimeError(f"ACP session limit reached (max {self._max_sessions}). Close idle ACP clients and retry.")
        session = AcpSession(
            session_id=sid, session_key=session_key, cwd=cwd,
            created_at=now_ms, last_touched_at=now_ms,
        )
        self._sessions[sid] = session
        return session

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def get_session(self, session_id: str) -> AcpSession | None:
        session = self._sessions.get(session_id)
        if session:
            self._touch(session)
        return session

    def get_session_by_run_id(self, run_id: str) -> AcpSession | None:
        sid = self._run_id_to_session_id.get(run_id)
        if not sid:
            return None
        return self.get_session(sid)

    def set_active_run(self, session_id: str, run_id: str, abort_controller: Any) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        session.active_run_id = run_id
        session.abort_controller = abort_controller
        self._run_id_to_session_id[run_id] = session_id
        self._touch(session)

    def clear_active_run(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        if session.active_run_id:
            self._run_id_to_session_id.pop(session.active_run_id, None)
        session.active_run_id = None
        session.abort_controller = None
        self._touch(session)

    def cancel_active_run(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session or not session.abort_controller:
            return False
        if hasattr(session.abort_controller, "abort"):
            session.abort_controller.abort()
        if session.active_run_id:
            self._run_id_to_session_id.pop(session.active_run_id, None)
        session.abort_controller = None
        session.active_run_id = None
        self._touch(session)
        return True

    def clear_all_sessions_for_test(self) -> None:
        for s in self._sessions.values():
            if s.abort_controller and hasattr(s.abort_controller, "abort"):
                s.abort_controller.abort()
        self._sessions.clear()
        self._run_id_to_session_id.clear()


default_acp_session_store = InMemorySessionStore()

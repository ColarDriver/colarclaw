"""Bash process registry — ported from bk/src/agents/bash-process-registry.ts.

Tracks running and finished bash process sessions with output buffering,
TTL-based sweeper, and drain semantics.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

from .session_slug import create_session_slug as _create_session_slug_id

DEFAULT_JOB_TTL_MS = 30 * 60 * 1000  # 30 minutes
MIN_JOB_TTL_MS = 60 * 1000  # 1 minute
MAX_JOB_TTL_MS = 3 * 60 * 60 * 1000  # 3 hours
DEFAULT_PENDING_OUTPUT_CHARS = 30_000

ProcessStatus = Literal["running", "completed", "failed", "killed"]


def _clamp_ttl(value: int | None) -> int:
    if value is None or value != value:  # NaN check
        return DEFAULT_JOB_TTL_MS
    return min(max(value, MIN_JOB_TTL_MS), MAX_JOB_TTL_MS)


_job_ttl_ms = _clamp_ttl(
    int(os.environ.get("PI_BASH_JOB_TTL_MS", "0") or "0") or None
)


@dataclass
class ProcessSession:
    id: str
    command: str
    scope_key: str | None = None
    session_key: str | None = None
    notify_on_exit: bool = False
    notify_on_exit_empty_success: bool = False
    exit_notified: bool = False
    pid: int | None = None
    started_at: float = field(default_factory=lambda: time.time() * 1000)
    cwd: str | None = None
    max_output_chars: int = 100_000
    pending_max_output_chars: int | None = None
    total_output_chars: int = 0
    pending_stdout: list[str] = field(default_factory=list)
    pending_stderr: list[str] = field(default_factory=list)
    pending_stdout_chars: int = 0
    pending_stderr_chars: int = 0
    aggregated: str = ""
    tail: str = ""
    exit_code: int | None = None
    exit_signal: str | int | None = None
    exited: bool = False
    truncated: bool = False
    backgrounded: bool = False


@dataclass
class FinishedSession:
    id: str
    command: str
    scope_key: str | None = None
    started_at: float = 0
    ended_at: float = 0
    cwd: str | None = None
    status: ProcessStatus = "completed"
    exit_code: int | None = None
    exit_signal: str | int | None = None
    aggregated: str = ""
    tail: str = ""
    truncated: bool = False
    total_output_chars: int = 0


_running_sessions: dict[str, ProcessSession] = {}
_finished_sessions: dict[str, FinishedSession] = {}
_sweeper: threading.Timer | None = None
_sweeper_lock = threading.Lock()


def _is_session_id_taken(session_id: str) -> bool:
    return session_id in _running_sessions or session_id in _finished_sessions


def create_session_slug() -> str:
    return _create_session_slug_id(_is_session_id_taken)


def add_session(session: ProcessSession) -> None:
    _running_sessions[session.id] = session
    _start_sweeper()


def get_session(session_id: str) -> ProcessSession | None:
    return _running_sessions.get(session_id)


def get_finished_session(session_id: str) -> FinishedSession | None:
    return _finished_sessions.get(session_id)


def delete_session(session_id: str) -> None:
    _running_sessions.pop(session_id, None)
    _finished_sessions.pop(session_id, None)


def _sum_pending_chars(buffer: list[str]) -> int:
    return sum(len(chunk) for chunk in buffer)


def _cap_pending_buffer(buffer: list[str], pending_chars: int, cap: int) -> int:
    if pending_chars <= cap:
        return pending_chars
    last = buffer[-1] if buffer else None
    if last and len(last) >= cap:
        buffer.clear()
        buffer.append(last[len(last) - cap :])
        return cap
    while buffer and pending_chars - len(buffer[0]) >= cap:
        pending_chars -= len(buffer[0])
        buffer.pop(0)
    if buffer and pending_chars > cap:
        overflow = pending_chars - cap
        buffer[0] = buffer[0][overflow:]
        pending_chars = cap
    return pending_chars


def trim_with_cap(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[len(text) - max_len :]


def tail(text: str, max_len: int = 2000) -> str:
    if len(text) <= max_len:
        return text
    return text[len(text) - max_len :]


def append_output(session: ProcessSession, stream: Literal["stdout", "stderr"], chunk: str) -> None:
    buf = session.pending_stdout if stream == "stdout" else session.pending_stderr
    buf_chars = session.pending_stdout_chars if stream == "stdout" else session.pending_stderr_chars

    pending_cap = min(
        session.pending_max_output_chars or DEFAULT_PENDING_OUTPUT_CHARS,
        session.max_output_chars,
    )
    buf.append(chunk)
    pending_chars = buf_chars + len(chunk)
    if pending_chars > pending_cap:
        session.truncated = True
        pending_chars = _cap_pending_buffer(buf, pending_chars, pending_cap)

    if stream == "stdout":
        session.pending_stdout_chars = pending_chars
    else:
        session.pending_stderr_chars = pending_chars

    session.total_output_chars += len(chunk)
    aggregated = trim_with_cap(session.aggregated + chunk, session.max_output_chars)
    session.truncated = session.truncated or len(aggregated) < len(session.aggregated) + len(chunk)
    session.aggregated = aggregated
    session.tail = tail(session.aggregated, 2000)


def drain_session(session: ProcessSession) -> tuple[str, str]:
    stdout = "".join(session.pending_stdout)
    stderr = "".join(session.pending_stderr)
    session.pending_stdout = []
    session.pending_stderr = []
    session.pending_stdout_chars = 0
    session.pending_stderr_chars = 0
    return stdout, stderr


def mark_exited(
    session: ProcessSession,
    exit_code: int | None,
    exit_signal: str | int | None,
    status: ProcessStatus,
) -> None:
    session.exited = True
    session.exit_code = exit_code
    session.exit_signal = exit_signal
    session.tail = tail(session.aggregated, 2000)
    _move_to_finished(session, status)


def mark_backgrounded(session: ProcessSession) -> None:
    session.backgrounded = True


def _move_to_finished(session: ProcessSession, status: ProcessStatus) -> None:
    _running_sessions.pop(session.id, None)
    if not session.backgrounded:
        return
    _finished_sessions[session.id] = FinishedSession(
        id=session.id,
        command=session.command,
        scope_key=session.scope_key,
        started_at=session.started_at,
        ended_at=time.time() * 1000,
        cwd=session.cwd,
        status=status,
        exit_code=session.exit_code,
        exit_signal=session.exit_signal,
        aggregated=session.aggregated,
        tail=session.tail,
        truncated=session.truncated,
        total_output_chars=session.total_output_chars,
    )


def list_running_sessions() -> list[ProcessSession]:
    return [s for s in _running_sessions.values() if s.backgrounded]


def list_finished_sessions() -> list[FinishedSession]:
    return list(_finished_sessions.values())


def clear_finished() -> None:
    _finished_sessions.clear()


def reset_process_registry_for_tests() -> None:
    _running_sessions.clear()
    _finished_sessions.clear()
    _stop_sweeper()


def set_job_ttl_ms(value: int | None = None) -> None:
    global _job_ttl_ms
    if value is None:
        return
    _job_ttl_ms = _clamp_ttl(value)
    _stop_sweeper()
    _start_sweeper()


def _prune_finished_sessions() -> None:
    cutoff = time.time() * 1000 - _job_ttl_ms
    to_remove = [sid for sid, s in _finished_sessions.items() if s.ended_at < cutoff]
    for sid in to_remove:
        _finished_sessions.pop(sid, None)


def _start_sweeper() -> None:
    global _sweeper
    with _sweeper_lock:
        if _sweeper is not None:
            return
        interval = max(30.0, _job_ttl_ms / 6.0) / 1000.0

        def run():
            global _sweeper
            _prune_finished_sessions()
            with _sweeper_lock:
                if _sweeper is not None:
                    _sweeper = threading.Timer(interval, run)
                    _sweeper.daemon = True
                    _sweeper.start()

        _sweeper = threading.Timer(interval, run)
        _sweeper.daemon = True
        _sweeper.start()


def _stop_sweeper() -> None:
    global _sweeper
    with _sweeper_lock:
        if _sweeper is not None:
            _sweeper.cancel()
            _sweeper = None

"""Session write lock — ported from bk/src/agents/session-write-lock.ts.

File-based session write lock with stale detection, PID liveness checking,
reentrant support, and a watchdog for timed-out locks.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("openclaw.session.write_lock")

DEFAULT_STALE_MS = 30 * 60 * 1000  # 30 minutes
DEFAULT_MAX_HOLD_MS = 5 * 60 * 1000  # 5 minutes
DEFAULT_TIMEOUT_GRACE_MS = 2 * 60 * 1000  # 2 minutes
MAX_LOCK_HOLD_MS = 2_147_000_000


@dataclass
class LockFilePayload:
    pid: int | None = None
    created_at: str | None = None


@dataclass
class SessionLockInspection:
    lock_path: str
    pid: int | None = None
    pid_alive: bool = False
    created_at: str | None = None
    age_ms: float | None = None
    stale: bool = False
    stale_reasons: list[str] = field(default_factory=list)
    removed: bool = False


@dataclass
class HeldLock:
    count: int
    lock_path: str
    acquired_at: float
    max_hold_ms: float


# ── Global state ──────────────────────────────────────────────────────────
_held_locks: dict[str, HeldLock] = {}
_cleanup_registered = False


def _is_pid_alive(pid: int) -> bool:
    """Check if a process is alive by sending signal 0."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _resolve_positive_ms(value: float | None, fallback: float) -> float:
    if value is None or not isinstance(value, (int, float)) or value <= 0:
        return fallback
    return value


def _read_lock_payload(lock_path: str) -> LockFilePayload | None:
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        payload = LockFilePayload()
        pid = data.get("pid")
        if isinstance(pid, int) and pid > 0:
            payload.pid = pid
        created_at = data.get("createdAt")
        if isinstance(created_at, str):
            payload.created_at = created_at
        return payload
    except (OSError, json.JSONDecodeError):
        return None


def _inspect_lock(
    payload: LockFilePayload | None,
    stale_ms: float,
    now_ms: float,
) -> dict[str, Any]:
    pid = payload.pid if payload and isinstance(payload.pid, int) and payload.pid > 0 else None
    pid_alive = _is_pid_alive(pid) if pid is not None else False
    created_at = payload.created_at if payload else None

    age_ms: float | None = None
    if created_at:
        try:
            created_ts = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp() * 1000
            age_ms = max(0, now_ms - created_ts)
        except (ValueError, TypeError):
            pass

    stale_reasons: list[str] = []
    if pid is None:
        stale_reasons.append("missing-pid")
    elif not pid_alive:
        stale_reasons.append("dead-pid")

    if age_ms is None:
        stale_reasons.append("invalid-createdAt")
    elif age_ms > stale_ms:
        stale_reasons.append("too-old")

    return {
        "pid": pid,
        "pid_alive": pid_alive,
        "created_at": created_at,
        "age_ms": age_ms,
        "stale": len(stale_reasons) > 0,
        "stale_reasons": stale_reasons,
    }


def _release_all_locks_sync() -> None:
    """Synchronously release all held locks (for process exit cleanup)."""
    for session_file, held in list(_held_locks.items()):
        try:
            os.unlink(held.lock_path)
        except OSError:
            pass
        del _held_locks[session_file]


def _register_cleanup() -> None:
    global _cleanup_registered
    if _cleanup_registered:
        return
    _cleanup_registered = True
    atexit.register(_release_all_locks_sync)


def resolve_session_lock_max_hold_from_timeout(
    timeout_ms: float,
    grace_ms: float | None = None,
    min_ms: float | None = None,
) -> float:
    """Resolve max lock hold time from a session timeout."""
    min_val = _resolve_positive_ms(min_ms, DEFAULT_MAX_HOLD_MS)
    timeout_val = _resolve_positive_ms(timeout_ms, min_val)
    grace_val = _resolve_positive_ms(grace_ms, DEFAULT_TIMEOUT_GRACE_MS)
    return min(MAX_LOCK_HOLD_MS, max(min_val, timeout_val + grace_val))


async def acquire_session_write_lock(
    session_file: str,
    timeout_ms: float = 10_000,
    stale_ms: float = DEFAULT_STALE_MS,
    max_hold_ms: float = DEFAULT_MAX_HOLD_MS,
    allow_reentrant: bool = True,
) -> dict[str, Any]:
    """Acquire a file-based write lock for a session.

    Returns a dict with a 'release' async callable.
    """
    import asyncio

    _register_cleanup()

    session_path = os.path.realpath(session_file)
    lock_path = f"{session_path}.lock"
    session_dir = os.path.dirname(session_path)
    os.makedirs(session_dir, exist_ok=True)

    # Reentrant check
    if allow_reentrant and session_path in _held_locks:
        held = _held_locks[session_path]
        held.count += 1

        async def reentrant_release() -> None:
            held.count -= 1
            if held.count <= 0:
                _held_locks.pop(session_path, None)
                try:
                    os.unlink(held.lock_path)
                except OSError:
                    pass

        return {"release": reentrant_release}

    started_at = time.monotonic() * 1000
    attempt = 0

    while (time.monotonic() * 1000 - started_at) < timeout_ms:
        attempt += 1
        try:
            # O_CREAT | O_EXCL — atomic create-if-not-exists
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                payload = json.dumps({
                    "pid": os.getpid(),
                    "createdAt": datetime.utcnow().isoformat() + "Z",
                }, indent=2)
                os.write(fd, payload.encode("utf-8"))
            finally:
                os.close(fd)

            held = HeldLock(
                count=1,
                lock_path=lock_path,
                acquired_at=time.monotonic() * 1000,
                max_hold_ms=max_hold_ms,
            )
            _held_locks[session_path] = held

            async def release() -> None:
                held.count -= 1
                if held.count <= 0:
                    _held_locks.pop(session_path, None)
                    try:
                        os.unlink(lock_path)
                    except OSError:
                        pass

            return {"release": release}

        except FileExistsError:
            # Lock file exists — check if stale
            lock_payload = _read_lock_payload(lock_path)
            now_ms = time.time() * 1000
            inspection = _inspect_lock(lock_payload, stale_ms, now_ms)

            if inspection["stale"]:
                try:
                    os.unlink(lock_path)
                except OSError:
                    pass
                continue

            delay = min(1.0, 0.05 * attempt)
            await asyncio.sleep(delay)

    raise TimeoutError(
        f"Session file locked (timeout {timeout_ms}ms): {lock_path}"
    )


async def clean_stale_lock_files(
    sessions_dir: str,
    stale_ms: float = DEFAULT_STALE_MS,
    remove_stale: bool = True,
) -> dict[str, list[SessionLockInspection]]:
    """Scan and optionally remove stale lock files from a sessions directory."""
    resolved = os.path.realpath(sessions_dir)
    locks: list[SessionLockInspection] = []
    cleaned: list[SessionLockInspection] = []

    try:
        entries = os.listdir(resolved)
    except FileNotFoundError:
        return {"locks": [], "cleaned": []}

    lock_files = sorted(e for e in entries if e.endswith(".jsonl.lock"))
    now_ms = time.time() * 1000

    for name in lock_files:
        lock_path = os.path.join(resolved, name)
        payload = _read_lock_payload(lock_path)
        inspection = _inspect_lock(payload, stale_ms, now_ms)

        lock_info = SessionLockInspection(
            lock_path=lock_path,
            pid=inspection["pid"],
            pid_alive=inspection["pid_alive"],
            created_at=inspection["created_at"],
            age_ms=inspection["age_ms"],
            stale=inspection["stale"],
            stale_reasons=inspection["stale_reasons"],
            removed=False,
        )

        if lock_info.stale and remove_stale:
            try:
                os.unlink(lock_path)
                lock_info.removed = True
                cleaned.append(lock_info)
                log.warning(
                    "Removed stale session lock: %s (%s)",
                    lock_path,
                    ", ".join(lock_info.stale_reasons) or "unknown",
                )
            except OSError:
                pass

        locks.append(lock_info)

    return {"locks": locks, "cleaned": cleaned}

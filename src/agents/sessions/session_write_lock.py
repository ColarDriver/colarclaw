"""Session write lock — ported from bk/src/agents/session-write-lock.ts.

File-based locking to prevent concurrent writes to session files.
Includes stale lock detection, PID liveness checks, and watchdog.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("openclaw.agents.session_write_lock")

LOCK_FILE_SUFFIX = ".lock"
STALE_LOCK_THRESHOLD_MS = 30_000
WATCHDOG_INTERVAL_MS = 60_000
MAX_LOCK_AGE_MS = 10 * 60 * 1000  # 10 minutes


@dataclass
class LockInfo:
    pid: int
    created_at: float
    session_id: str | None = None
    host: str | None = None


@dataclass
class LockAcquireResult:
    acquired: bool
    lock_path: str = ""
    error: str | None = None
    stale_cleaned: bool = False


class SessionWriteLock:
    """Manages a file-based write lock for session files."""

    def __init__(self, session_path: str, session_id: str | None = None):
        self._session_path = session_path
        self._session_id = session_id
        self._lock_path = session_path + LOCK_FILE_SUFFIX
        self._held = False
        self._watchdog: threading.Timer | None = None
        self._lock = threading.Lock()

    @property
    def lock_path(self) -> str:
        return self._lock_path

    @property
    def is_held(self) -> bool:
        return self._held

    def acquire(self, timeout_ms: float = 5000) -> LockAcquireResult:
        """Attempt to acquire the write lock."""
        stale_cleaned = False

        # Check for existing lock
        existing = self._read_lock_file()
        if existing is not None:
            if self._is_stale_lock(existing):
                log.info("Cleaning stale lock: pid=%d path=%s", existing.pid, self._lock_path)
                self._remove_lock_file()
                stale_cleaned = True
            else:
                return LockAcquireResult(
                    acquired=False,
                    lock_path=self._lock_path,
                    error=f"Lock held by pid {existing.pid}",
                )

        # Write lock file
        try:
            self._write_lock_file()
            self._held = True
            self._start_watchdog()
            return LockAcquireResult(
                acquired=True,
                lock_path=self._lock_path,
                stale_cleaned=stale_cleaned,
            )
        except Exception as exc:
            return LockAcquireResult(
                acquired=False,
                lock_path=self._lock_path,
                error=str(exc),
            )

    def release(self) -> bool:
        """Release the write lock."""
        with self._lock:
            if not self._held:
                return False
            self._stop_watchdog()
            self._remove_lock_file()
            self._held = False
            return True

    def _read_lock_file(self) -> LockInfo | None:
        try:
            with open(self._lock_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return LockInfo(
                pid=data.get("pid", 0),
                created_at=data.get("createdAt", 0),
                session_id=data.get("sessionId"),
                host=data.get("host"),
            )
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            return None

    def _write_lock_file(self) -> None:
        import socket
        lock_data = {
            "pid": os.getpid(),
            "createdAt": time.time() * 1000,
            "sessionId": self._session_id,
            "host": socket.gethostname(),
        }
        os.makedirs(os.path.dirname(self._lock_path), exist_ok=True)
        # Use exclusive create to prevent races
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                json.dump(lock_data, f)
        except FileExistsError:
            # Overwrite if we confirmed stale earlier
            with open(self._lock_path, "w", encoding="utf-8") as f:
                json.dump(lock_data, f)

    def _remove_lock_file(self) -> None:
        try:
            os.unlink(self._lock_path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            log.warning("Failed to remove lock file %s: %s", self._lock_path, exc)

    def _is_stale_lock(self, info: LockInfo) -> bool:
        now = time.time() * 1000
        age = now - info.created_at

        # Too old => stale
        if age > MAX_LOCK_AGE_MS:
            return True

        # Check if PID is still alive
        if not _is_process_alive(info.pid):
            return True

        # If within threshold, not stale
        if age < STALE_LOCK_THRESHOLD_MS:
            return False

        return False

    def _start_watchdog(self) -> None:
        interval = WATCHDOG_INTERVAL_MS / 1000.0

        def _check():
            with self._lock:
                if not self._held:
                    return
                # Check if lock is still ours
                existing = self._read_lock_file()
                if existing and existing.pid != os.getpid():
                    log.warning("Lock was stolen by pid %d", existing.pid)
                    self._held = False
                    return
                # Refresh watchdog
                self._watchdog = threading.Timer(interval, _check)
                self._watchdog.daemon = True
                self._watchdog.start()

        self._watchdog = threading.Timer(interval, _check)
        self._watchdog.daemon = True
        self._watchdog.start()

    def _stop_watchdog(self) -> None:
        if self._watchdog:
            self._watchdog.cancel()
            self._watchdog = None

    def __enter__(self):
        result = self.acquire()
        if not result.acquired:
            raise RuntimeError(f"Failed to acquire lock: {result.error}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


def _is_process_alive(pid: int) -> bool:
    """Check if a process is alive by sending signal 0."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we don't have permission


def acquire_session_write_lock(
    session_path: str,
    session_id: str | None = None,
) -> SessionWriteLock:
    """Create and acquire a session write lock. Raises if lock can't be acquired."""
    lock = SessionWriteLock(session_path, session_id)
    result = lock.acquire()
    if not result.acquired:
        raise RuntimeError(f"Failed to acquire session write lock: {result.error}")
    return lock

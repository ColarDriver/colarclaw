"""Infra process — ported from bk/src/infra/abort-signal.ts, backoff.ts,
dedupe.ts, pid-file.ts, process-signal.ts, shutdown.ts, lifecycle.ts,
startup-banner.ts, singleton.ts, lazy.ts, once.ts, retry.ts.

Process lifecycle: abort signals, backoff, dedup cache, PID files, shutdown,
startup, singleton management, lazy initialization, retry logic.
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import signal
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# ─── abort-signal.ts ───

_abort_event = asyncio.Event()


def create_abort_controller() -> dict[str, Any]:
    event = asyncio.Event()
    return {"signal": event, "abort": event.set, "aborted": event.is_set}


def is_abort_error(err: Any) -> bool:
    return isinstance(err, (asyncio.CancelledError, KeyboardInterrupt))


# ─── backoff.ts ───

@dataclass
class BackoffPolicy:
    initial_ms: int = 1000
    max_ms: int = 60_000
    factor: float = 2.0
    jitter: float = 0.1


def compute_backoff(policy: BackoffPolicy, attempt: int) -> int:
    base = policy.initial_ms * (policy.factor ** max(attempt - 1, 0))
    jitter = base * policy.jitter * random.random()
    return min(policy.max_ms, round(base + jitter))


async def sleep_with_abort(ms: int, abort_event: asyncio.Event | None = None) -> None:
    if ms <= 0:
        return
    try:
        if abort_event:
            await asyncio.wait_for(abort_event.wait(), timeout=ms / 1000.0)
            raise asyncio.CancelledError("aborted")
        else:
            await asyncio.sleep(ms / 1000.0)
    except asyncio.TimeoutError:
        pass


# ─── dedupe.ts ───

class DedupeCache:
    def __init__(self, ttl_ms: int = 60_000, max_size: int = 1000):
        self._ttl_ms = max(0, ttl_ms)
        self._max_size = max(0, max_size)
        self._cache: OrderedDict[str, float] = OrderedDict()

    def check(self, key: str | None, now: float | None = None) -> bool:
        if not key:
            return False
        now = now or time.time() * 1000
        if self._has_unexpired(key, now, touch=True):
            return True
        self._touch(key, now)
        self._prune(now)
        return False

    def peek(self, key: str | None, now: float | None = None) -> bool:
        if not key:
            return False
        now = now or time.time() * 1000
        return self._has_unexpired(key, now, touch=False)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    def _has_unexpired(self, key: str, now: float, touch: bool) -> bool:
        ts = self._cache.get(key)
        if ts is None:
            return False
        if self._ttl_ms > 0 and now - ts >= self._ttl_ms:
            del self._cache[key]
            return False
        if touch:
            self._touch(key, now)
        return True

    def _touch(self, key: str, now: float) -> None:
        if key in self._cache:
            del self._cache[key]
        self._cache[key] = now

    def _prune(self, now: float) -> None:
        if self._ttl_ms > 0:
            cutoff = now - self._ttl_ms
            expired = [k for k, v in self._cache.items() if v < cutoff]
            for k in expired:
                del self._cache[k]
        while len(self._cache) > self._max_size > 0:
            self._cache.popitem(last=False)


def create_dedupe_cache(ttl_ms: int = 60_000, max_size: int = 1000) -> DedupeCache:
    return DedupeCache(ttl_ms=ttl_ms, max_size=max_size)


# ─── pid-file.ts ───

def write_pid_file(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(str(os.getpid()))


def read_pid_file(path: str) -> int | None:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def remove_pid_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


# ─── shutdown.ts / lifecycle.ts ───

_shutdown_handlers: list[Callable[..., Any]] = []
_shutdown_complete = False


def on_shutdown(handler: Callable[..., Any]) -> Callable[[], None]:
    _shutdown_handlers.append(handler)
    def dispose():
        try:
            _shutdown_handlers.remove(handler)
        except ValueError:
            pass
    return dispose


async def run_shutdown_handlers() -> None:
    global _shutdown_complete
    if _shutdown_complete:
        return
    _shutdown_complete = True
    for handler in reversed(_shutdown_handlers):
        try:
            result = handler()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass
    _shutdown_handlers.clear()


def install_signal_handlers() -> None:
    def handler(signum, frame):
        asyncio.get_event_loop().create_task(run_shutdown_handlers())
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


# ─── startup-banner.ts ───

def format_startup_banner(name: str = "OpenClaw", version: str = "0.0.0", port: int | None = None) -> str:
    lines = [f"╔══════════════════════════════════╗"]
    lines.append(f"║  {name} v{version}".ljust(35) + "║")
    if port:
        lines.append(f"║  Listening on port {port}".ljust(35) + "║")
    lines.append(f"╚══════════════════════════════════╝")
    return "\n".join(lines)


# ─── singleton.ts ───

class Singleton:
    _instances: dict[str, Any] = {}

    @classmethod
    def get_or_create(cls, key: str, factory: Callable[[], T]) -> T:
        if key not in cls._instances:
            cls._instances[key] = factory()
        return cls._instances[key]

    @classmethod
    def clear(cls, key: str | None = None) -> None:
        if key:
            cls._instances.pop(key, None)
        else:
            cls._instances.clear()


# ─── lazy.ts ───

class Lazy:
    def __init__(self, factory: Callable[[], T]):
        self._factory = factory
        self._value: T | None = None
        self._initialized = False

    @property
    def value(self) -> T:
        if not self._initialized:
            self._value = self._factory()
            self._initialized = True
        return self._value  # type: ignore

    def reset(self) -> None:
        self._value = None
        self._initialized = False


# ─── once.ts ───

class Once:
    def __init__(self):
        self._called = False
        self._result: Any = None

    def call(self, fn: Callable[..., T], *args: Any) -> T:
        if not self._called:
            self._result = fn(*args)
            self._called = True
        return self._result

    def reset(self) -> None:
        self._called = False
        self._result = None


# ─── retry.ts ───

async def retry_async(fn: Callable[..., Any], max_attempts: int = 3,
                       policy: BackoffPolicy | None = None,
                       should_retry: Callable[[Exception], bool] | None = None) -> Any:
    p = policy or BackoffPolicy()
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            if attempt == max_attempts:
                raise
            if should_retry and not should_retry(e):
                raise
            delay = compute_backoff(p, attempt)
            await asyncio.sleep(delay / 1000.0)
    raise last_error or RuntimeError("retry exhausted")


def retry_sync(fn: Callable[..., T], max_attempts: int = 3,
               policy: BackoffPolicy | None = None) -> T:
    p = policy or BackoffPolicy()
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt == max_attempts:
                raise
            delay = compute_backoff(p, attempt)
            time.sleep(delay / 1000.0)
    raise last_error or RuntimeError("retry exhausted")

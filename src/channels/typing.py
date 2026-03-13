"""Channels typing — ported from bk/src/channels/typing.ts,
typing-lifecycle.ts, typing-start-guard.ts.

Typing indicator lifecycle management with keepalive timers,
circuit-breaker start guard, and TTL safety auto-stop.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger("channels.typing")


# ─── typing-start-guard.ts ───

class TypingStartGuard:
    """Circuit breaker for typing indicator start calls.

    Stops keepalive loop after N consecutive failures.
    """

    def __init__(
        self,
        is_sealed: Callable[[], bool],
        on_start_error: Callable[[Exception], None],
        max_consecutive_failures: int = 2,
        on_trip: Callable[[], None] | None = None,
    ):
        self._is_sealed = is_sealed
        self._on_start_error = on_start_error
        self._max_failures = max(1, max_consecutive_failures)
        self._on_trip = on_trip
        self._consecutive_failures = 0
        self._tripped = False

    async def run(self, fn: Callable[[], Any]) -> None:
        if self._tripped or self._is_sealed():
            return
        try:
            await fn()
            self._consecutive_failures = 0
        except Exception as e:
            self._consecutive_failures += 1
            self._on_start_error(e)
            if self._consecutive_failures >= self._max_failures:
                self._tripped = True
                if self._on_trip:
                    self._on_trip()

    def reset(self) -> None:
        self._consecutive_failures = 0
        self._tripped = False

    def is_tripped(self) -> bool:
        return self._tripped


# ─── typing-lifecycle.ts ───

class TypingKeepaliveLoop:
    """Periodic keepalive for typing indicators."""

    def __init__(self, interval_ms: int, on_tick: Callable[[], Any]):
        self._interval_ms = interval_ms
        self._on_tick = on_tick
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._interval_ms / 1000.0)
                if not self._running:
                    break
                await self._on_tick()
        except asyncio.CancelledError:
            pass


# ─── typing.ts ───

@dataclass
class TypingCallbacksConfig:
    keepalive_interval_ms: int = 3000
    max_consecutive_failures: int = 2
    max_duration_ms: int = 60_000


class TypingCallbacks:
    """Typing indicator controller with keepalive, circuit breaker, and TTL safety."""

    def __init__(
        self,
        start: Callable[[], Any],
        stop: Callable[[], Any] | None = None,
        on_start_error: Callable[[Exception], None] | None = None,
        on_stop_error: Callable[[Exception], None] | None = None,
        config: TypingCallbacksConfig | None = None,
    ):
        cfg = config or TypingCallbacksConfig()
        self._start_fn = start
        self._stop_fn = stop
        self._on_start_error = on_start_error or (lambda e: logger.warning(f"typing start error: {e}"))
        self._on_stop_error = on_stop_error or self._on_start_error
        self._stop_sent = False
        self._closed = False
        self._ttl_task: asyncio.Task | None = None
        self._max_duration_ms = cfg.max_duration_ms

        self._start_guard = TypingStartGuard(
            is_sealed=lambda: self._closed,
            on_start_error=self._on_start_error,
            max_consecutive_failures=cfg.max_consecutive_failures,
            on_trip=lambda: self._keepalive.stop(),
        )

        self._keepalive = TypingKeepaliveLoop(
            interval_ms=cfg.keepalive_interval_ms,
            on_tick=lambda: self._fire_start(),
        )

    async def _fire_start(self) -> None:
        await self._start_guard.run(self._start_fn)

    def _fire_stop(self) -> None:
        self._closed = True
        self._keepalive.stop()
        self._cancel_ttl()
        if not self._stop_fn or self._stop_sent:
            return
        self._stop_sent = True
        asyncio.create_task(self._safe_stop())

    async def _safe_stop(self) -> None:
        try:
            await self._stop_fn()
        except Exception as e:
            self._on_stop_error(e)

    def _cancel_ttl(self) -> None:
        if self._ttl_task and not self._ttl_task.done():
            self._ttl_task.cancel()
        self._ttl_task = None

    def _start_ttl_timer(self) -> None:
        if self._max_duration_ms <= 0:
            return
        self._cancel_ttl()

        async def _ttl():
            await asyncio.sleep(self._max_duration_ms / 1000.0)
            if not self._closed:
                logger.warning(f"typing TTL exceeded ({self._max_duration_ms}ms), auto-stopping")
                self._fire_stop()

        self._ttl_task = asyncio.create_task(_ttl())

    async def on_reply_start(self) -> None:
        """Called when a reply starts — start typing indicator."""
        if self._closed:
            return
        self._stop_sent = False
        self._start_guard.reset()
        self._keepalive.stop()
        self._cancel_ttl()
        await self._fire_start()
        if self._start_guard.is_tripped():
            return
        self._keepalive.start()
        self._start_ttl_timer()

    def on_idle(self) -> None:
        """Called when idle — stop typing indicator."""
        self._fire_stop()

    def on_cleanup(self) -> None:
        """Called on cleanup — stop typing indicator."""
        self._fire_stop()


# ─── typing-start-guard.ts (additional) ───

@dataclass
class TypingLifecycleConfig:
    enabled: bool = True
    keepalive_interval_ms: int = 3000


# ─── inbound-debounce-policy.ts ───

@dataclass
class InboundDebouncePolicy:
    """Policy for debouncing rapid inbound messages."""
    debounce_ms: int = 0
    max_batch_size: int = 1
    merge_strategy: str = "last"  # "last" | "concat" | "first"


def resolve_inbound_debounce(
    channel_config: dict[str, Any] | None = None,
) -> InboundDebouncePolicy:
    """Resolve inbound debounce policy from channel config."""
    if not channel_config:
        return InboundDebouncePolicy()
    debounce = channel_config.get("inboundDebounce")
    if not debounce or not isinstance(debounce, dict):
        return InboundDebouncePolicy()
    return InboundDebouncePolicy(
        debounce_ms=debounce.get("debounceMs", 0),
        max_batch_size=debounce.get("maxBatchSize", 1),
        merge_strategy=debounce.get("mergeStrategy", "last"),
    )

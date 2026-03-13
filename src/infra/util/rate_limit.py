"""Infra rate_limit — ported from bk/src/infra/fixed-window-rate-limit.ts.

Fixed-window rate limiter for throttling requests.
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool = True
    retry_after_ms: float = 0.0
    remaining: int = 0


class FixedWindowRateLimiter:
    """Fixed-window rate limiter."""

    def __init__(self, max_requests: int, window_ms: float, now_fn: Any = None):
        self._max_requests = max(1, int(max_requests))
        self._window_ms = max(1, int(window_ms))
        self._now_fn = now_fn or (lambda: time.time() * 1000)
        self._count = 0
        self._window_start_ms = 0.0

    def consume(self) -> RateLimitResult:
        """Try to consume a request. Returns whether it was allowed."""
        now_ms = self._now_fn()
        if now_ms - self._window_start_ms >= self._window_ms:
            self._window_start_ms = now_ms
            self._count = 0

        if self._count >= self._max_requests:
            return RateLimitResult(
                allowed=False,
                retry_after_ms=max(0, self._window_start_ms + self._window_ms - now_ms),
                remaining=0,
            )

        self._count += 1
        return RateLimitResult(
            allowed=True,
            retry_after_ms=0,
            remaining=max(0, self._max_requests - self._count),
        )

    def reset(self) -> None:
        self._count = 0
        self._window_start_ms = 0.0


from typing import Any

"""Plugin SDK webhooks — ported from bk/src/plugin-sdk/webhook-*.ts.

Webhook target management, request guards, body reading, path normalization.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable


def normalize_webhook_path(raw: str) -> str:
    trimmed = raw.strip().lstrip("/")
    return f"/{trimmed}" if trimmed else "/"


def resolve_webhook_path(base: str, sub: str) -> str:
    return f"{normalize_webhook_path(base).rstrip('/')}{normalize_webhook_path(sub)}"


@dataclass
class WebhookTargetMatchResult:
    matched: bool = False
    target_id: str = ""
    account_id: str | None = None
    auth_token: str | None = None


@dataclass
class RegisterWebhookTargetOptions:
    target_id: str = ""
    account_id: str | None = None
    auth_token: str | None = None
    path: str = ""


_webhook_targets: dict[str, RegisterWebhookTargetOptions] = {}


def register_webhook_target(opts: RegisterWebhookTargetOptions) -> None:
    _webhook_targets[opts.target_id] = opts


def resolve_webhook_targets(path: str) -> list[WebhookTargetMatchResult]:
    results: list[WebhookTargetMatchResult] = []
    for tid, opts in _webhook_targets.items():
        if opts.path and path.startswith(opts.path):
            results.append(WebhookTargetMatchResult(matched=True, target_id=tid, account_id=opts.account_id, auth_token=opts.auth_token))
    return results


def resolve_single_webhook_target(path: str) -> WebhookTargetMatchResult | None:
    matches = resolve_webhook_targets(path)
    return matches[0] if matches else None


# Request guards
WEBHOOK_BODY_READ_DEFAULTS = {"max_bytes": 1 * 1024 * 1024, "timeout_ms": 10_000}
WEBHOOK_IN_FLIGHT_DEFAULTS = {"max_concurrent": 100}
DEFAULT_WEBHOOK_BODY_TIMEOUT_MS = 10_000
DEFAULT_WEBHOOK_MAX_BODY_BYTES = 1 * 1024 * 1024


def is_json_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    return "application/json" in content_type.lower()


async def read_webhook_body(request: Any, max_bytes: int = DEFAULT_WEBHOOK_MAX_BODY_BYTES) -> bytes:
    """Read webhook request body with limit (placeholder)."""
    return b""


class WebhookInFlightLimiter:
    def __init__(self, max_concurrent: int = 100):
        self._max = max_concurrent
        self._current = 0

    def try_acquire(self) -> bool:
        if self._current >= self._max:
            return False
        self._current += 1
        return True

    def release(self) -> None:
        self._current = max(0, self._current - 1)


# Memory guards
@dataclass
class BoundedCounter:
    limit: int = 1000
    window_ms: int = 60_000
    _count: int = 0
    _window_start: float = 0.0

    def increment(self) -> bool:
        now = time.time() * 1000
        if now - self._window_start > self.window_ms:
            self._count = 0
            self._window_start = now
        self._count += 1
        return self._count <= self.limit


def create_bounded_counter(limit: int = 1000, window_ms: int = 60_000) -> BoundedCounter:
    return BoundedCounter(limit=limit, window_ms=window_ms)


class FixedWindowRateLimiter:
    def __init__(self, limit: int = 100, window_ms: int = 60_000):
        self._counter = BoundedCounter(limit=limit, window_ms=window_ms)

    def check(self) -> bool:
        return self._counter.increment()


def create_fixed_window_rate_limiter(limit: int = 100, window_ms: int = 60_000) -> FixedWindowRateLimiter:
    return FixedWindowRateLimiter(limit=limit, window_ms=window_ms)

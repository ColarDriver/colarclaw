"""Gateway auth — ported from bk/src/gateway/ auth files.

Authentication, authorization, rate limiting, credentials, and install policy.
Consolidates: auth.ts, auth-config-utils.ts, auth-install-policy.ts,
  auth-mode-policy.ts, auth-rate-limit.ts, credentials.ts, device-auth.ts,
  http-auth-helpers.ts, input-allowlist.ts.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal

AuthMode = Literal["none", "token", "device"]


# ─── auth-rate-limit.ts ───

@dataclass
class RateLimitBucket:
    tokens: int
    max_tokens: int
    refill_rate: float  # tokens per second
    last_refill_ms: int = 0

    def try_consume(self, count: int = 1) -> bool:
        now = int(time.time() * 1000)
        elapsed_s = (now - self.last_refill_ms) / 1000.0
        refill = int(elapsed_s * self.refill_rate)
        if refill > 0:
            self.tokens = min(self.max_tokens, self.tokens + refill)
            self.last_refill_ms = now
        if self.tokens >= count:
            self.tokens -= count
            return True
        return False


class AuthRateLimiter:
    """Per-IP rate limiter for auth attempts."""

    def __init__(
        self,
        max_attempts: int = 10,
        window_seconds: float = 60.0,
    ) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._buckets: OrderedDict[str, RateLimitBucket] = OrderedDict()
        self._max_entries = 10000

    def is_allowed(self, key: str) -> bool:
        bucket = self._buckets.get(key)
        if not bucket:
            bucket = RateLimitBucket(
                tokens=self._max,
                max_tokens=self._max,
                refill_rate=self._max / self._window,
                last_refill_ms=int(time.time() * 1000),
            )
            self._buckets[key] = bucket
            if len(self._buckets) > self._max_entries:
                self._buckets.popitem(last=False)
        return bucket.try_consume()


# ─── auth-config-utils.ts ───

def resolve_auth_mode(cfg: dict[str, Any]) -> AuthMode:
    """Resolve auth mode from config."""
    gateway = cfg.get("gateway", {})
    if not isinstance(gateway, dict):
        return "none"
    mode = str(gateway.get("authMode", "")).strip().lower()
    if mode in ("token", "device"):
        return mode  # type: ignore[return-value]
    return "none"


def resolve_auth_token_from_config(cfg: dict[str, Any]) -> str | None:
    """Resolve the gateway auth token from config."""
    gateway = cfg.get("gateway", {})
    if not isinstance(gateway, dict):
        return None
    token = gateway.get("authToken")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


# ─── auth-install-policy.ts ───

def resolve_install_policy(cfg: dict[str, Any]) -> str:
    """Resolve install policy (open, approval, deny)."""
    gateway = cfg.get("gateway", {})
    policy = str(gateway.get("installPolicy", "")).strip().lower() if isinstance(gateway, dict) else ""
    return policy if policy in ("open", "approval", "deny") else "approval"


# ─── auth-mode-policy.ts ───

def resolve_auth_mode_policy(cfg: dict[str, Any]) -> dict[str, Any]:
    """Resolve auth mode policy details."""
    mode = resolve_auth_mode(cfg)
    return {
        "mode": mode,
        "requires_token": mode == "token",
        "requires_device": mode == "device",
        "allow_anonymous": mode == "none",
    }


# ─── credentials.ts ───

def hash_token(token: str) -> str:
    """Hash a bearer token for storage/comparison."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, stored_hash: str) -> bool:
    """Verify a token against its hash."""
    return hmac.compare_digest(hash_token(token), stored_hash)


# ─── input-allowlist.ts ───

@dataclass
class InputAllowlistEntry:
    pattern: str = ""
    compiled: re.Pattern[str] | None = None


class InputAllowlist:
    """Allowlist for input validation."""

    def __init__(self) -> None:
        self._entries: list[InputAllowlistEntry] = []

    def add(self, pattern: str) -> None:
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            self._entries.append(InputAllowlistEntry(pattern=pattern, compiled=compiled))
        except re.error:
            pass

    def is_allowed(self, value: str) -> bool:
        if not self._entries:
            return True  # No allowlist = allow all
        return any(
            e.compiled and e.compiled.search(value)
            for e in self._entries
        )

    def clear(self) -> None:
        self._entries.clear()

"""Infra dedupe — ported from bk/src/infra/dedupe.ts, map-size.ts,
canvas-host-url.ts, cli-root-options.ts, gemini-auth.ts,
control-ui-assets.ts, ws.ts.

Deduplication cache, canvas host URL resolution, CLI root options,
Gemini auth, WebSocket helpers, UI asset resolution.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any


# ─── map-size.ts ───

def prune_dict_to_max_size(d: dict[Any, Any], max_size: int) -> None:
    """Prune a dict to max_size by removing oldest entries."""
    limit = max(0, int(max_size))
    if limit <= 0:
        d.clear()
        return
    while len(d) > limit:
        oldest_key = next(iter(d))
        del d[oldest_key]


# ─── dedupe.ts ───

class DedupeCache:
    """Time-windowed deduplication cache."""

    def __init__(self, ttl_ms: float = 60_000, max_size: int = 1000):
        self._ttl_ms = max(0, ttl_ms)
        self._max_size = max(0, int(max_size))
        self._cache: dict[str, float] = {}

    def check(self, key: str | None, now: float | None = None) -> bool:
        """Check+insert. Returns True if key was already present (duplicate)."""
        if not key:
            return False
        now_ms = now or time.time() * 1000
        if self._has_unexpired(key, now_ms, touch=True):
            return True
        self._touch(key, now_ms)
        self._prune(now_ms)
        return False

    def peek(self, key: str | None, now: float | None = None) -> bool:
        """Check without inserting."""
        if not key:
            return False
        now_ms = now or time.time() * 1000
        return self._has_unexpired(key, now_ms, touch=False)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    def _touch(self, key: str, now_ms: float) -> None:
        if key in self._cache:
            del self._cache[key]
        self._cache[key] = now_ms

    def _prune(self, now_ms: float) -> None:
        if self._ttl_ms > 0:
            cutoff = now_ms - self._ttl_ms
            expired = [k for k, v in self._cache.items() if v < cutoff]
            for k in expired:
                del self._cache[k]
        prune_dict_to_max_size(self._cache, self._max_size)

    def _has_unexpired(self, key: str, now_ms: float, touch: bool) -> bool:
        ts = self._cache.get(key)
        if ts is None:
            return False
        if self._ttl_ms > 0 and now_ms - ts >= self._ttl_ms:
            del self._cache[key]
            return False
        if touch:
            self._touch(key, now_ms)
        return True


# ─── canvas-host-url.ts ───

def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def _normalize_host(value: str | None, reject_loopback: bool = False) -> str:
    if not value:
        return ""
    trimmed = value.strip()
    if not trimmed:
        return ""
    if reject_loopback and _is_loopback_host(trimmed):
        return ""
    return trimmed


def _parse_host_header(value: str | None) -> tuple[str, int | None]:
    """Parse host header返回 (host, port)."""
    if not value:
        return "", None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(f"http://{value.strip()}")
        port = parsed.port
        return parsed.hostname or "", port
    except Exception:
        return "", None


def resolve_canvas_host_url(
    canvas_port: int | None = None,
    host_override: str | None = None,
    request_host: str | None = None,
    forwarded_proto: str | None = None,
    local_address: str | None = None,
    scheme: str | None = None,
) -> str | None:
    """Resolve the canvas host URL."""
    port = canvas_port
    if not port:
        return None

    proto = scheme
    if not proto:
        fp = forwarded_proto.strip() if forwarded_proto else ""
        proto = "https" if fp == "https" else "http"

    override = _normalize_host(host_override, reject_loopback=True)
    req_host, req_port = _parse_host_header(request_host)
    req_host_str = _normalize_host(req_host, reject_loopback=bool(override))
    local_addr = _normalize_host(local_address, reject_loopback=bool(override or req_host_str))

    host = override or req_host_str or local_addr
    if not host:
        return None

    exposed_port = port
    if not override and req_host_str and port == 18789:
        if req_port and req_port > 0:
            exposed_port = req_port
        elif proto == "https":
            exposed_port = 443
        elif proto == "http":
            exposed_port = 80

    formatted = f"[{host}]" if ":" in host else host
    return f"{proto}://{formatted}:{exposed_port}"


# ─── cli-root-options.ts ───

FLAG_TERMINATOR = "--"
_ROOT_BOOLEAN_FLAGS = {"--dev", "--no-color"}
_ROOT_VALUE_FLAGS = {"--profile", "--log-level"}


def is_value_token(arg: str | None) -> bool:
    if not arg or arg == FLAG_TERMINATOR:
        return False
    if not arg.startswith("-"):
        return True
    return bool(re.match(r"^-\d+(?:\.\d+)?$", arg))


def consume_root_option_token(args: list[str], index: int) -> int:
    """Consume root option tokens. Returns number of tokens consumed."""
    if index >= len(args):
        return 0
    arg = args[index]
    if arg in _ROOT_BOOLEAN_FLAGS:
        return 1
    if arg.startswith("--profile=") or arg.startswith("--log-level="):
        return 1
    if arg in _ROOT_VALUE_FLAGS:
        next_val = args[index + 1] if index + 1 < len(args) else None
        return 2 if is_value_token(next_val) else 1
    return 0


# ─── gemini-auth.ts ───

def parse_gemini_auth(api_key: str) -> dict[str, str]:
    """Parse Gemini API key and return appropriate auth headers."""
    if api_key.startswith("{"):
        try:
            parsed = json.loads(api_key)
            token = parsed.get("token", "")
            if isinstance(token, str) and token:
                return {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
        except (json.JSONDecodeError, AttributeError):
            pass
    return {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }


# ─── control-ui-assets.ts ───

def resolve_control_ui_assets_dir(root: str | None = None) -> str | None:
    """Resolve the directory containing control UI (web) assets."""
    candidates = []
    if root:
        candidates.append(os.path.join(root, "dist", "web"))
        candidates.append(os.path.join(root, "web", "dist"))
        candidates.append(os.path.join(root, "public"))
    candidates.append(os.path.join(os.path.dirname(__file__), "..", "..", "web", "dist"))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return os.path.abspath(candidate)
    return None


# ─── ws.ts ───

def raw_data_to_string(data: Any, encoding: str = "utf-8") -> str:
    """Convert raw WebSocket data to string."""
    if isinstance(data, str):
        return data
    if isinstance(data, bytes):
        return data.decode(encoding, errors="replace")
    if isinstance(data, bytearray):
        return bytes(data).decode(encoding, errors="replace")
    if isinstance(data, memoryview):
        return bytes(data).decode(encoding, errors="replace")
    return str(data)

"""Shared utility functions.

Ported from bk/src/utils/ (~18 TS files).

Covers string helpers, object manipulation, retry logic,
debounce/throttle, deep merge, hash generation, URL parsing,
semver comparison, and random ID generation.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import os
import re
import time
import uuid
from typing import Any, Callable, TypeVar

__all__ = [
    "generate_id", "deep_merge", "deep_clone",
    "retry", "debounce", "throttle",
    "parse_semver", "compare_semver",
    "slugify", "truncate", "pluralize",
    "chunk_list", "unique", "group_by",
    "sha256_hex", "md5_hex",
    "parse_url_params", "build_url",
]

T = TypeVar("T")


# ─── ID generation ───

def generate_id(*, prefix: str = "", length: int = 12) -> str:
    """Generate a random ID."""
    uid = uuid.uuid4().hex[:length]
    return f"{prefix}{uid}" if prefix else uid


def generate_uuid() -> str:
    return str(uuid.uuid4())


# ─── Deep merge ───

def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dicts (override wins)."""
    result = {**base}
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def deep_clone(obj: Any) -> Any:
    """Deep clone an object."""
    import copy
    return copy.deepcopy(obj)


# ─── Retry ───

async def retry(
    fn: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    delay_ms: int = 1000,
    backoff: float = 2.0,
    on_error: Callable[[Exception, int], None] | None = None,
) -> Any:
    """Retry an async function with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn(*args)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            last_error = e
            if on_error:
                on_error(e, attempt)
            if attempt < max_attempts:
                wait = delay_ms * (backoff ** (attempt - 1)) / 1000
                await asyncio.sleep(wait)
    raise last_error or RuntimeError("Retry exhausted")


# ─── Debounce / Throttle ───

def debounce(delay_ms: int) -> Callable:
    """Decorator that debounces a function call."""
    def decorator(fn: Callable) -> Callable:
        timer: dict[str, Any] = {"task": None}

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> None:
            if timer["task"]:
                timer["task"].cancel()

            async def delayed() -> None:
                await asyncio.sleep(delay_ms / 1000)
                await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)

            timer["task"] = asyncio.create_task(delayed())

        return wrapper
    return decorator


def throttle(interval_ms: int) -> Callable:
    """Decorator that throttles a function call."""
    def decorator(fn: Callable) -> Callable:
        last_call: dict[str, float] = {"ts": 0}

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            now = time.time()
            if now - last_call["ts"] < interval_ms / 1000:
                return None
            last_call["ts"] = now
            return fn(*args, **kwargs)

        return wrapper
    return decorator


# ─── Semver ───

def parse_semver(version: str) -> tuple[int, int, int, str]:
    """Parse a semver string into (major, minor, patch, pre)."""
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(.+))?$", version)
    if not match:
        return (0, 0, 0, "")
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        match.group(4) or "",
    )


def compare_semver(a: str, b: str) -> int:
    """Compare two semver strings. Returns -1, 0, or 1."""
    av = parse_semver(a)
    bv = parse_semver(b)
    for i in range(3):
        if av[i] < bv[i]:
            return -1
        if av[i] > bv[i]:
            return 1
    # Pre-release vs release
    if av[3] and not bv[3]:
        return -1
    if not av[3] and bv[3]:
        return 1
    return 0


# ─── String helpers ───

def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def truncate(text: str, max_length: int, *, suffix: str = "…") -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def pluralize(word: str, count: int) -> str:
    return word if count == 1 else f"{word}s"


# ─── Collection helpers ───

def chunk_list(lst: list[T], size: int) -> list[list[T]]:
    """Split a list into chunks of given size."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


def unique(lst: list[T]) -> list[T]:
    """Deduplicate a list preserving order."""
    seen: set = set()
    result: list[T] = []
    for item in lst:
        key = id(item) if not isinstance(item, (str, int, float, bool)) else item
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def group_by(lst: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    """Group a list of dicts by a key."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in lst:
        k = str(item.get(key, ""))
        if k not in groups:
            groups[k] = []
        groups[k].append(item)
    return groups


# ─── Hash helpers ───

def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def md5_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.md5(data).hexdigest()


# ─── URL helpers ───

def parse_url_params(url: str) -> dict[str, str]:
    """Parse query parameters from a URL."""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    return {k: v[0] for k, v in parse_qs(parsed.query).items()}


def build_url(base: str, params: dict[str, str]) -> str:
    """Build a URL with query parameters."""
    from urllib.parse import urlencode
    if not params:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode(params)}"

"""Infra formatting — ported from bk/src/infra/format-time/*.ts,
source-display.ts, logger.ts, logging-setup.ts, sanitize-path.ts,
redact.ts, obfuscate.ts, string-normalize.ts, token-counter.ts, etc.

Time formatting, logging setup, text processing, token counting.
"""
from __future__ import annotations

import datetime
import logging
import os
import re
import time
from typing import Any


# ─── format-time/format-datetime.ts ───

def format_datetime(ts: float | int | None = None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    dt = datetime.datetime.fromtimestamp(ts or time.time())
    return dt.strftime(fmt)


def format_iso_datetime(ts: float | int | None = None) -> str:
    dt = datetime.datetime.fromtimestamp(ts or time.time(), tz=datetime.timezone.utc)
    return dt.isoformat()


# ─── format-time/format-duration.ts ───

def format_duration_ms(ms: int | float) -> str:
    if ms < 1000:
        return f"{int(ms)}ms"
    seconds = ms / 1000.0
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60.0
    return f"{hours:.1f}h"


def format_duration_seconds(s: float) -> str:
    return format_duration_ms(s * 1000)


# ─── format-time/format-relative.ts ───

def format_relative_time(ts: float, now: float | None = None) -> str:
    now = now or time.time()
    diff = now - ts
    if diff < 0:
        return "in the future"
    if diff < 60:
        return "just now"
    if diff < 3600:
        m = int(diff / 60)
        return f"{m}m ago"
    if diff < 86400:
        h = int(diff / 3600)
        return f"{h}h ago"
    d = int(diff / 86400)
    return f"{d}d ago"


# ─── source-display.ts ───

def format_source_display(source: str, max_length: int = 60) -> str:
    if len(source) <= max_length:
        return source
    return f"...{source[-(max_length - 3):]}"


# ─── sanitize-path.ts ───

def sanitize_path_for_display(path: str) -> str:
    home = os.path.expanduser("~")
    if path.startswith(home):
        return f"~{path[len(home):]}"
    return path


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    sanitized = sanitized.strip('. ')
    return sanitized or "unnamed"


# ─── redact.ts ───

_SENSITIVE_PATTERNS = [
    re.compile(r'(sk-[a-zA-Z0-9]{20,})'),
    re.compile(r'(ghp_[a-zA-Z0-9]{36,})'),
    re.compile(r'(ghu_[a-zA-Z0-9]{36,})'),
    re.compile(r'(xox[bpsa]-[a-zA-Z0-9-]+)'),
    re.compile(r'(AIza[a-zA-Z0-9_-]{35})'),
    re.compile(r'(eyJ[a-zA-Z0-9_-]{20,}\.eyJ[a-zA-Z0-9_-]{20,})'),
]


def redact_sensitive_text(text: str) -> str:
    result = text
    for pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub(lambda m: m.group(0)[:8] + "..." + m.group(0)[-4:], result)
    return result


# ─── obfuscate.ts ───

def obfuscate_string(value: str, visible_chars: int = 4) -> str:
    if len(value) <= visible_chars:
        return "*" * len(value)
    return value[:visible_chars] + "*" * (len(value) - visible_chars)


def obfuscate_api_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


# ─── string-normalize.ts ───

def normalize_string_entries(entries: list[Any]) -> list[str]:
    return [str(e).strip() for e in entries if str(e).strip()]


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_multiline(text: str) -> str:
    lines = text.split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


# ─── token-counter.ts ───

def estimate_token_count(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK."""
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
    ascii_count = len(text) - cjk_count
    return int(ascii_count / 4 + cjk_count / 2) + 1


def is_within_token_budget(text: str, budget: int) -> bool:
    return estimate_token_count(text) <= budget


# ─── logger.ts / logging-setup.ts ───

def create_subsystem_logger(name: str, level: str = "INFO") -> logging.Logger:
    log = logging.getLogger(f"openclaw.{name}")
    log.setLevel(getattr(logging, level.upper(), logging.INFO))
    return log


def setup_logging(level: str = "INFO", format: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=format)


def set_log_level(level: str) -> None:
    logging.getLogger("openclaw").setLevel(getattr(logging, level.upper(), logging.INFO))

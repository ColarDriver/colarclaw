"""Security policies and access control.

Ported from bk/src/security/ (~19 TS files, ~7.6k lines).

Covers policy enforcement, content safety, input sanitization,
rate limiting, IP allowlisting, CORS, and audit logging.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Security policy ───

@dataclass
class SecurityPolicy:
    """Top-level security policy."""
    allow_bash: bool = False
    allow_file_write: bool = False
    allow_network: bool = True
    require_approval: str = "dangerous"  # "all" | "dangerous" | "none"
    sandbox_mode: str = "none"  # "none" | "docker" | "e2b"
    max_request_size_bytes: int = 10 * 1024 * 1024
    rate_limit_enabled: bool = True
    rate_limit_rpm: int = 60
    ip_allowlist: list[str] = field(default_factory=list)
    ip_blocklist: list[str] = field(default_factory=list)
    cors_origins: list[str] = field(default_factory=list)
    csrf_enabled: bool = True
    content_filter_enabled: bool = True


def resolve_security_policy(config: dict[str, Any]) -> SecurityPolicy:
    """Resolve security policy from config."""
    sec = config.get("security", {}) or {}
    approvals = config.get("approvals", {}) or {}
    return SecurityPolicy(
        allow_bash=bool(sec.get("allowBash", False)),
        allow_file_write=bool(sec.get("allowFileWrite", False)),
        allow_network=bool(sec.get("allowNetwork", True)),
        require_approval=approvals.get("mode", "dangerous"),
        sandbox_mode=sec.get("sandboxMode", "none"),
        max_request_size_bytes=int(sec.get("maxRequestSizeBytes", 10 * 1024 * 1024)),
        rate_limit_enabled=bool(sec.get("rateLimitEnabled", True)),
        rate_limit_rpm=int(sec.get("rateLimitRpm", 60)),
        ip_allowlist=sec.get("ipAllowlist", []),
        ip_blocklist=sec.get("ipBlocklist", []),
        cors_origins=sec.get("corsOrigins", []),
        csrf_enabled=bool(sec.get("csrfEnabled", True)),
    )


# ─── Rate limiter ───

class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, *, max_per_minute: int = 60, per_key: bool = True):
        self._max_rpm = max_per_minute
        self._per_key = per_key
        self._buckets: dict[str, list[float]] = {}

    def check(self, key: str = "global") -> bool:
        """Check if a request is allowed. Returns True if allowed."""
        bucket_key = key if self._per_key else "global"
        now = time.time()
        window_start = now - 60

        if bucket_key not in self._buckets:
            self._buckets[bucket_key] = []

        # Prune old entries
        self._buckets[bucket_key] = [
            t for t in self._buckets[bucket_key] if t > window_start
        ]

        if len(self._buckets[bucket_key]) >= self._max_rpm:
            return False

        self._buckets[bucket_key].append(now)
        return True

    def reset(self, key: str | None = None) -> None:
        if key:
            self._buckets.pop(key, None)
        else:
            self._buckets.clear()


# ─── IP filtering ───

def check_ip_allowed(
    ip: str,
    *,
    allowlist: list[str] | None = None,
    blocklist: list[str] | None = None,
) -> bool:
    """Check if an IP is allowed based on allow/block lists."""
    if blocklist:
        for pattern in blocklist:
            if _ip_matches(ip, pattern):
                return False
    if allowlist:
        return any(_ip_matches(ip, pattern) for pattern in allowlist)
    return True


def _ip_matches(ip: str, pattern: str) -> bool:
    """Check if an IP matches a pattern (exact, CIDR, or wildcard)."""
    if ip == pattern:
        return True
    if "*" in pattern:
        regex = pattern.replace(".", r"\.").replace("*", r"\d+")
        return bool(re.match(f"^{regex}$", ip))
    if "/" in pattern:
        return _cidr_match(ip, pattern)
    return False


def _cidr_match(ip: str, cidr: str) -> bool:
    """Check if an IP falls within a CIDR range."""
    try:
        parts = cidr.split("/")
        network = parts[0]
        prefix = int(parts[1])
        ip_int = _ip_to_int(ip)
        net_int = _ip_to_int(network)
        mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        return (ip_int & mask) == (net_int & mask)
    except (ValueError, IndexError):
        return False


def _ip_to_int(ip: str) -> int:
    parts = ip.split(".")
    return sum(int(p) << (8 * (3 - i)) for i, p in enumerate(parts))


# ─── Content safety ───

CONTENT_FILTER_PATTERNS = [
    re.compile(r"(?:DROP|DELETE|TRUNCATE)\s+(?:TABLE|DATABASE)", re.IGNORECASE),
    re.compile(r"(?:rm\s+-rf\s+/|format\s+[cC]:)", re.IGNORECASE),
    re.compile(r"(?:curl|wget)\s+.*\|\s*(?:ba)?sh", re.IGNORECASE),
]


def check_content_safety(text: str) -> list[str]:
    """Check text for potentially dangerous content patterns."""
    warnings = []
    for pattern in CONTENT_FILTER_PATTERNS:
        if pattern.search(text):
            warnings.append(f"Matched dangerous pattern: {pattern.pattern[:50]}")
    return warnings


# ─── Input sanitization ───

def sanitize_user_input(text: str, *, max_length: int = 100_000) -> str:
    """Sanitize user input text."""
    if len(text) > max_length:
        text = text[:max_length]
    # Strip null bytes
    text = text.replace("\x00", "")
    return text


def sanitize_terminal_text(text: str) -> str:
    """Sanitize text for safe terminal display (strip ANSI escapes)."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


# ─── CSRF token ───

def generate_csrf_token(session_id: str, secret: str) -> str:
    """Generate a CSRF token."""
    return hmac.new(
        secret.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_csrf_token(token: str, session_id: str, secret: str) -> bool:
    """Verify a CSRF token."""
    expected = generate_csrf_token(session_id, secret)
    return hmac.compare_digest(token, expected)


# ─── CORS ───

def build_cors_headers(
    origin: str,
    *,
    allowed_origins: list[str] | None = None,
) -> dict[str, str]:
    """Build CORS response headers."""
    headers: dict[str, str] = {}

    if not allowed_origins:
        return headers

    if "*" in allowed_origins or origin in allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        headers["Access-Control-Max-Age"] = "86400"

    return headers


# ─── Audit logging ───

@dataclass
class AuditEvent:
    """An audit log event."""
    timestamp: str = ""
    event_type: str = ""
    source_ip: str = ""
    user_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    severity: str = "info"  # "info" | "warning" | "critical"


class AuditLogger:
    """Security audit log writer."""

    def __init__(self, log_path: str = ""):
        self._log_path = log_path
        self._events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        self._events.append(event)
        if self._log_path:
            import json
            try:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "ts": event.timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "type": event.event_type,
                        "ip": event.source_ip,
                        "user": event.user_id,
                        "severity": event.severity,
                        **event.details,
                    }) + "\n")
            except Exception:
                pass

    def query(self, *, event_type: str = "", limit: int = 100) -> list[AuditEvent]:
        results = self._events
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        return results[-limit:]

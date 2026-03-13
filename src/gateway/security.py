"""Gateway security — ported from bk/src/gateway/security-path.ts,
origin-check.ts, server.auth.shared.ts, auth-config-utils.ts,
auth-install-policy.ts, auth-mode-policy.ts, auth-rate-limit.ts,
startup-auth.ts, startup-control-ui-origins.ts, probe-auth.ts, probe.ts,
http-auth-helpers.ts, http-common.ts, http-endpoint-helpers.ts, http-utils.ts,
role-policy.ts, resolve-configured-secret-input-string.ts, input-allowlist.ts,
server/http-auth.ts.

Security: path traversal protection, origin checks, auth policies,
rate limiting, HTTP auth helpers, role enforcement, and secret resolution.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── security-path.ts — Path traversal protection ───

_PATH_TRAVERSAL_RE = re.compile(r'(?:^|[/\\])\.\.(?:[/\\]|$)')
_NULL_BYTE_RE = re.compile(r'\x00')


def is_safe_path(path: str) -> bool:
    """Check if a path is safe from traversal attacks."""
    if not path:
        return True
    if _NULL_BYTE_RE.search(path):
        return False
    if _PATH_TRAVERSAL_RE.search(path):
        return False
    # Absolute paths are suspicious in request URIs
    if path.startswith("/") and ".." in path:
        return False
    return True


def sanitize_request_path(path: str) -> str:
    """Sanitize a request path, removing dangerous components."""
    # Remove null bytes
    cleaned = _NULL_BYTE_RE.sub("", path)
    # Normalize double slashes
    cleaned = re.sub(r'/+', '/', cleaned)
    # Remove trailing slash (except bare /)
    if len(cleaned) > 1 and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned


# ─── origin-check.ts — CSRF origin validation ───

def check_origin(
    origin: str | None,
    host: str | None,
    *,
    allowed_origins: list[str] | None = None,
    allow_null_origin: bool = False,
) -> bool:
    """Validate request origin against host and allow-list for CSRF protection.

    Returns True if the origin is valid.
    """
    if not origin:
        return allow_null_origin

    origin_normalized = origin.strip().lower().rstrip("/")

    # Always allow loopback
    for prefix in ("http://localhost", "http://127.0.0.1", "http://[::1]",
                    "https://localhost", "https://127.0.0.1", "https://[::1]"):
        if origin_normalized.startswith(prefix):
            return True

    # Check against host header
    if host:
        host_normalized = host.strip().lower()
        from urllib.parse import urlparse
        parsed = urlparse(origin_normalized)
        origin_host = parsed.hostname or ""
        if origin_host == host_normalized or origin_host == host_normalized.split(":")[0]:
            return True

    # Check allow-list
    if allowed_origins:
        for allowed in allowed_origins:
            if allowed == "*":
                return True
            if allowed.strip().lower().rstrip("/") == origin_normalized:
                return True

    return False


# ─── role-policy.ts ───

ROLES = {
    "operator": {"operator.admin", "operator.read", "operator.write",
                 "operator.approvals", "operator.pairing"},
    "viewer": {"operator.read"},
    "controller": {"operator.read", "operator.write"},
    "node": {"node"},
}


def resolve_role_scopes(role: str) -> set[str]:
    """Resolve the scopes for a given role."""
    return ROLES.get(role, set())


def check_role_scope(role: str, required_scope: str) -> bool:
    """Check if a role has a required scope."""
    scopes = resolve_role_scopes(role)
    return required_scope in scopes or "operator.admin" in scopes


# ─── auth-mode-policy.ts — Auth mode enforcement ───

AUTH_MODES = {"none", "token", "password", "token-or-password", "tailscale", "device"}


def validate_auth_mode(mode: str) -> bool:
    """Validate an auth mode string."""
    return mode.lower() in AUTH_MODES


@dataclass
class AuthModePolicy:
    """Policy for an auth mode."""
    mode: str = "none"
    requires_token: bool = False
    requires_password: bool = False
    requires_device_auth: bool = False
    allows_anonymous: bool = True


def resolve_auth_mode_policy(mode: str) -> AuthModePolicy:
    """Resolve policy for a given auth mode."""
    m = mode.lower()
    if m == "none":
        return AuthModePolicy(mode=m, allows_anonymous=True)
    if m == "token":
        return AuthModePolicy(mode=m, requires_token=True, allows_anonymous=False)
    if m == "password":
        return AuthModePolicy(mode=m, requires_password=True, allows_anonymous=False)
    if m == "token-or-password":
        return AuthModePolicy(mode=m, requires_token=True, requires_password=True,
                              allows_anonymous=False)
    if m == "device":
        return AuthModePolicy(mode=m, requires_device_auth=True, allows_anonymous=False)
    if m == "tailscale":
        return AuthModePolicy(mode=m, allows_anonymous=False)
    return AuthModePolicy(mode=m)


# ─── auth-install-policy.ts ───

def should_enforce_auth_on_install(cfg: dict[str, Any]) -> bool:
    """Check if auth should be enforced during install/setup."""
    gateway_cfg = cfg.get("gateway", {}) or {}
    auth_cfg = gateway_cfg.get("auth", {}) or {}
    mode = auth_cfg.get("mode", "none")
    return mode != "none"


# ─── auth-rate-limit.ts — Brute-force protection ───

@dataclass
class AuthRateLimitEntry:
    """Rate limit entry for an IP address."""
    attempts: int = 0
    first_attempt_ms: int = 0
    last_attempt_ms: int = 0
    blocked_until_ms: int = 0


class AuthRateLimiter:
    """Token-bucket rate limiter for auth attempts (per-IP).

    Prevents brute-force attacks against the gateway auth endpoint.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 10,
        window_ms: int = 60_000,
        block_duration_ms: int = 300_000,  # 5 minutes
    ) -> None:
        self._max_attempts = max_attempts
        self._window_ms = window_ms
        self._block_duration_ms = block_duration_ms
        self._entries: dict[str, AuthRateLimitEntry] = {}

    def check(self, ip: str) -> bool:
        """Check if an IP is allowed to attempt auth. Returns True if allowed."""
        entry = self._entries.get(ip)
        now = int(time.time() * 1000)

        if entry and entry.blocked_until_ms > now:
            return False

        if entry and now - entry.first_attempt_ms > self._window_ms:
            # Window expired, reset
            entry.attempts = 0
            entry.first_attempt_ms = now

        return True

    def record_attempt(self, ip: str, *, success: bool = False) -> None:
        """Record an auth attempt."""
        now = int(time.time() * 1000)

        if ip not in self._entries:
            self._entries[ip] = AuthRateLimitEntry(first_attempt_ms=now)
        entry = self._entries[ip]

        if success:
            # Successful auth resets the counter
            entry.attempts = 0
            entry.blocked_until_ms = 0
            return

        entry.attempts += 1
        entry.last_attempt_ms = now

        if entry.attempts >= self._max_attempts:
            entry.blocked_until_ms = now + self._block_duration_ms
            logger.warning(
                f"auth rate limit: IP {ip} blocked for "
                f"{self._block_duration_ms // 1000}s after {entry.attempts} failed attempts"
            )

    def is_blocked(self, ip: str) -> bool:
        """Check if an IP is currently blocked."""
        entry = self._entries.get(ip)
        if not entry:
            return False
        return entry.blocked_until_ms > int(time.time() * 1000)

    def cleanup(self) -> None:
        """Remove expired entries."""
        now = int(time.time() * 1000)
        expired = [
            ip for ip, entry in self._entries.items()
            if (now - entry.last_attempt_ms > self._window_ms
                and entry.blocked_until_ms < now)
        ]
        for ip in expired:
            del self._entries[ip]


# ─── http-auth-helpers.ts — Bearer token extraction ───

_BEARER_RE = re.compile(r'^Bearer\s+(.+)$', re.I)


def extract_bearer_token(authorization: str | None) -> str | None:
    """Extract a Bearer token from an Authorization header."""
    if not authorization:
        return None
    match = _BEARER_RE.match(authorization.strip())
    return match.group(1).strip() if match else None


def verify_token(provided: str, expected: str) -> bool:
    """Constant-time token comparison."""
    return hmac.compare_digest(provided.encode(), expected.encode())


def verify_password(provided: str, expected_hash: str) -> bool:
    """Verify a password against a stored hash.

    For gateway auth, passwords are typically compared directly (not hashed)
    since they're stored as config values, not user-managed credentials.
    """
    return hmac.compare_digest(provided.encode(), expected_hash.encode())


# ─── http-utils.ts ───

def parse_content_type(header: str | None) -> str:
    """Parse Content-Type header, returning the MIME type without parameters."""
    if not header:
        return ""
    return header.split(";")[0].strip().lower()


def is_json_content_type(header: str | None) -> bool:
    """Check if Content-Type is JSON."""
    ct = parse_content_type(header)
    return ct in ("application/json", "text/json")


# ─── input-allowlist.ts ───

def is_input_allowed(
    text: str,
    allowlist: list[str] | None = None,
) -> bool:
    """Check if input text is allowed by the allowlist."""
    if not allowlist:
        return True
    return text.strip() in allowlist


# ─── resolve-configured-secret-input-string.ts ───

SECRET_REF_PREFIX = "secret://"


def is_secret_ref(value: str) -> bool:
    """Check if a value is a secret reference (secret://path)."""
    return isinstance(value, str) and value.strip().startswith(SECRET_REF_PREFIX)


def parse_secret_ref(value: str) -> str | None:
    """Parse a secret reference, returning the secret path."""
    if not is_secret_ref(value):
        return None
    return value.strip()[len(SECRET_REF_PREFIX):]


# ─── startup-auth.ts — Auth initialization ───

@dataclass
class ResolvedGatewayAuth:
    """Resolved gateway authentication configuration."""
    mode: str = "none"
    token: str | None = None
    password: str | None = None
    device_auth_enabled: bool = False
    tailscale_enabled: bool = False
    allowed_tailscale_users: list[str] = field(default_factory=list)


def resolve_gateway_auth(cfg: dict[str, Any]) -> ResolvedGatewayAuth:
    """Resolve gateway auth from configuration."""
    gateway_cfg = cfg.get("gateway", {}) or {}
    auth_cfg = gateway_cfg.get("auth", {}) or {}

    mode = auth_cfg.get("mode", "none")
    token = auth_cfg.get("token")
    password = auth_cfg.get("password")
    tailscale_cfg = auth_cfg.get("tailscale", {}) or {}

    # Token from env takes precedence
    env_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if env_token:
        token = env_token.strip()

    return ResolvedGatewayAuth(
        mode=mode,
        token=token if isinstance(token, str) and token.strip() else None,
        password=password if isinstance(password, str) and password.strip() else None,
        device_auth_enabled=mode == "device",
        tailscale_enabled=mode == "tailscale",
        allowed_tailscale_users=tailscale_cfg.get("allowedUsers", []),
    )


# ─── startup-control-ui-origins.ts ───

def resolve_control_ui_origins(cfg: dict[str, Any]) -> list[str]:
    """Resolve allowed origins for the control UI from config."""
    gateway_cfg = cfg.get("gateway", {}) or {}
    control_ui_cfg = gateway_cfg.get("controlUi", {}) or {}
    origins = control_ui_cfg.get("allowedOrigins", [])
    if not isinstance(origins, list):
        return []
    return [o.strip() for o in origins if isinstance(o, str) and o.strip()]

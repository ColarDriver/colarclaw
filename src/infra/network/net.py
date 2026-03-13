"""Infra net — ported from bk/src/infra/net/fetch-guard.ts, hostname.ts,
proxy-env.ts, proxy-fetch.ts, ssrf.ts, undici-global-dispatcher.ts.

Network security: SSRF guard, proxy environment, hostname normalization,
guarded fetch with redirect following, DNS pinning.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger("infra.net")


# ─── hostname.ts ───

def normalize_hostname(hostname: str) -> str:
    """Normalize a hostname: lowercase, strip trailing dot, unwrap brackets."""
    normalized = hostname.strip().lower().rstrip(".")
    if normalized.startswith("[") and normalized.endswith("]"):
        return normalized[1:-1]
    return normalized


# ─── proxy-env.ts ───

PROXY_ENV_KEYS = [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
]


def has_proxy_env_configured(env: dict[str, str] | None = None) -> bool:
    """Check if proxy environment variables are set."""
    e = env or os.environ
    for key in PROXY_ENV_KEYS:
        val = e.get(key, "").strip()
        if val:
            return True
    return False


def resolve_proxy_url(env: dict[str, str] | None = None) -> str | None:
    """Resolve proxy URL from environment."""
    e = env or os.environ
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        val = e.get(key, "").strip()
        if val:
            return val
    return None


def is_no_proxy(hostname: str, env: dict[str, str] | None = None) -> bool:
    """Check if hostname is in NO_PROXY list."""
    e = env or os.environ
    no_proxy = e.get("NO_PROXY", e.get("no_proxy", "")).strip()
    if not no_proxy:
        return False
    if no_proxy == "*":
        return True
    host_lower = hostname.strip().lower()
    for entry in no_proxy.split(","):
        entry = entry.strip().lower()
        if not entry:
            continue
        if entry.startswith("."):
            if host_lower.endswith(entry) or host_lower == entry[1:]:
                return True
        elif host_lower == entry:
            return True
    return False


# ─── ssrf.ts ───

_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/32"),
]


class SsrfBlockedError(Exception):
    """Raised when a URL is blocked by SSRF policy."""
    pass


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/internal."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in network for network in _PRIVATE_RANGES)
    except ValueError:
        return False


def resolve_pinned_hostname(hostname: str) -> list[str]:
    """Resolve hostname to IP addresses for DNS pinning."""
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return list({result[4][0] for result in results})
    except socket.gaierror:
        return []


def validate_ssrf_target(
    url: str,
    allow_private: bool = False,
) -> tuple[bool, str]:
    """Validate that a URL target is safe from SSRF.
    Returns (is_safe, reason).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "invalid URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"disallowed scheme: {parsed.scheme}"

    hostname = normalize_hostname(parsed.hostname or "")
    if not hostname:
        return False, "missing hostname"

    if not allow_private:
        # Check if hostname itself is an IP
        try:
            addr = ipaddress.ip_address(hostname)
            if is_private_ip(str(addr)):
                return False, f"private IP: {hostname}"
        except ValueError:
            # Not an IP literal — resolve DNS
            resolved = resolve_pinned_hostname(hostname)
            for ip in resolved:
                if is_private_ip(ip):
                    return False, f"hostname {hostname} resolves to private IP: {ip}"

    return True, "ok"


# ─── fetch-guard.ts ───

GUARDED_FETCH_MODE_STRICT = "strict"
GUARDED_FETCH_MODE_TRUSTED_ENV_PROXY = "trusted_env_proxy"

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}

_CROSS_ORIGIN_SAFE_HEADERS = {
    "accept", "accept-encoding", "accept-language", "cache-control",
    "content-language", "content-type", "if-match", "if-modified-since",
    "if-none-match", "if-unmodified-since", "pragma", "range", "user-agent",
}


@dataclass
class GuardedFetchResult:
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    final_url: str = ""
    ok: bool = False


async def guarded_fetch(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    max_redirects: int = 3,
    timeout_s: float = 30.0,
    allow_private: bool = False,
    mode: str = GUARDED_FETCH_MODE_STRICT,
) -> GuardedFetchResult:
    """Fetch with SSRF guard, DNS pinning, and redirect following."""
    import aiohttp

    if mode == GUARDED_FETCH_MODE_STRICT:
        safe, reason = validate_ssrf_target(url, allow_private=allow_private)
        if not safe:
            raise SsrfBlockedError(f"SSRF blocked: {reason}")

    visited: set[str] = set()
    current_url = url
    current_headers = dict(headers or {})
    redirect_count = 0

    try:
        async with aiohttp.ClientSession() as session:
            while True:
                visited.add(current_url)
                async with session.request(
                    method, current_url,
                    headers=current_headers,
                    data=body,
                    timeout=aiohttp.ClientTimeout(total=timeout_s),
                    allow_redirects=False,
                ) as response:
                    if response.status in _REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            raise ValueError(f"Redirect missing Location header ({response.status})")
                        redirect_count += 1
                        if redirect_count > max_redirects:
                            raise ValueError(f"Too many redirects (limit: {max_redirects})")
                        # Resolve relative URL
                        from urllib.parse import urljoin
                        next_url = urljoin(current_url, location)
                        if next_url in visited:
                            raise ValueError("Redirect loop detected")

                        # SSRF check the redirect target
                        if mode == GUARDED_FETCH_MODE_STRICT:
                            safe, reason = validate_ssrf_target(next_url, allow_private=allow_private)
                            if not safe:
                                raise SsrfBlockedError(f"SSRF blocked on redirect: {reason}")

                        # Cross-origin: strip sensitive headers
                        current_parsed = urlparse(current_url)
                        next_parsed = urlparse(next_url)
                        if current_parsed.netloc != next_parsed.netloc:
                            current_headers = {
                                k: v for k, v in current_headers.items()
                                if k.lower() in _CROSS_ORIGIN_SAFE_HEADERS
                            }

                        current_url = next_url
                        continue

                    resp_body = await response.read()
                    resp_headers = {k: v for k, v in response.headers.items()}
                    return GuardedFetchResult(
                        status=response.status,
                        headers=resp_headers,
                        body=resp_body,
                        final_url=current_url,
                        ok=200 <= response.status < 300,
                    )
    except ImportError:
        # Fallback without aiohttp
        from .core import fetch_with_timeout
        result = await fetch_with_timeout(url, method=method, headers=headers, timeout_s=timeout_s)
        return GuardedFetchResult(
            status=result.get("status", 0),
            headers=result.get("headers", {}),
            body=result.get("body", b""),
            final_url=url,
            ok=result.get("ok", False),
        )

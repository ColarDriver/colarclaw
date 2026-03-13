"""Infra networking — ported from bk/src/infra/fetch.ts, fixed-window-rate-limit.ts,
http-keepalive.ts, http-parse.ts, http-server-*.ts, network.ts, port.ts,
request-url.ts, ssrf-guard.ts, tls.ts, url-allowlist.ts, url-metadata.ts,
url-open.ts, url-sanitize.ts, websocket.ts.

HTTP client, rate limiting, server lifecycle, port management, SSRF protection,
URL processing, WebSocket management.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger("infra.network")


# ─── fetch.ts (Python: aiohttp wrapper) ───

async def fetch_with_timeout(url: str, timeout_s: float = 30.0, method: str = "GET",
                             headers: dict[str, str] | None = None, body: bytes | None = None,
                             max_retries: int = 0) -> dict[str, Any]:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=timeout_s)
            async with session.request(method, url, headers=headers, data=body, timeout=timeout) as resp:
                data = await resp.read()
                return {"status": resp.status, "headers": dict(resp.headers), "body": data, "ok": resp.ok}
    except Exception as e:
        return {"status": 0, "headers": {}, "body": b"", "ok": False, "error": str(e)}


# ─── fixed-window-rate-limit.ts ───

@dataclass
class FixedWindowRateLimiter:
    limit: int = 100
    window_ms: int = 60_000
    _count: int = 0
    _window_start: float = 0.0

    def check(self, now: float | None = None) -> bool:
        now = now or time.time() * 1000
        if now - self._window_start > self.window_ms:
            self._count = 0
            self._window_start = now
        self._count += 1
        return self._count <= self.limit

    def remaining(self) -> int:
        return max(0, self.limit - self._count)

    def reset(self) -> None:
        self._count = 0
        self._window_start = 0.0


def create_fixed_window_rate_limiter(limit: int = 100, window_ms: int = 60_000) -> FixedWindowRateLimiter:
    return FixedWindowRateLimiter(limit=limit, window_ms=window_ms)


# ─── port.ts ───

async def find_available_port(start: int = 3000, end: int = 9000) -> int | None:
    import socket
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect((host, port))
            return True
    except (OSError, ConnectionRefusedError):
        return False


# ─── ssrf-guard.ts ───

SSRF_BLOCKED_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}
SSRF_BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data"}
SSRF_METADATA_IPS = {"169.254.169.254", "fd00::"}


def is_ssrf_safe_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "invalid URL"
    scheme = (parsed.scheme or "").lower()
    if scheme in SSRF_BLOCKED_SCHEMES:
        return False, f"blocked scheme: {scheme}"
    hostname = (parsed.hostname or "").lower()
    if hostname in SSRF_BLOCKED_HOSTNAMES:
        return False, f"blocked hostname: {hostname}"
    if hostname in SSRF_METADATA_IPS:
        return False, "cloud metadata endpoint"
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            return False, "private/loopback IP"
    except ValueError:
        pass
    return True, "ok"


def guard_ssrf(url: str) -> None:
    safe, reason = is_ssrf_safe_url(url)
    if not safe:
        raise ValueError(f"SSRF blocked: {reason} ({url})")


# ─── url-sanitize.ts ───

def sanitize_url(url: str) -> str:
    trimmed = url.strip()
    if not trimmed:
        return ""
    parsed = urlparse(trimmed)
    if not parsed.scheme:
        trimmed = f"https://{trimmed}"
    return trimmed


def extract_base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# ─── url-allowlist.ts ───

def is_url_in_allowlist(url: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    parsed = urlparse(url.lower())
    hostname = parsed.hostname or ""
    for pattern in allowlist:
        pattern = pattern.strip().lower()
        if not pattern:
            continue
        if hostname == pattern or hostname.endswith(f".{pattern}"):
            return True
    return False


# ─── url-metadata.ts ───

@dataclass
class UrlMetadata:
    url: str = ""
    scheme: str = ""
    hostname: str = ""
    port: int | None = None
    path: str = ""
    query: str | None = None
    fragment: str | None = None


def parse_url_metadata(url: str) -> UrlMetadata:
    parsed = urlparse(url)
    return UrlMetadata(
        url=url, scheme=parsed.scheme, hostname=parsed.hostname or "",
        port=parsed.port, path=parsed.path,
        query=parsed.query or None, fragment=parsed.fragment or None,
    )


# ─── request-url.ts ───

def resolve_request_url(base: str, path: str, query: dict[str, str] | None = None) -> str:
    from urllib.parse import urlencode
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if query:
        url += f"?{urlencode(query)}"
    return url


# ─── http-server support ───

@dataclass
class HttpServerConfig:
    host: str = "0.0.0.0"
    port: int = 3000
    tls: bool = False
    cert_path: str | None = None
    key_path: str | None = None


# ─── websocket ───

@dataclass
class WebSocketConnection:
    url: str = ""
    connected: bool = False
    error: str | None = None


async def create_websocket_connection(url: str, headers: dict[str, str] | None = None) -> WebSocketConnection:
    """Placeholder WebSocket connection."""
    return WebSocketConnection(url=url)


# ─── http-keepalive ───

def create_http_keepalive_agent(max_sockets: int = 50, max_free_sockets: int = 10,
                                 timeout_ms: int = 60_000, free_socket_timeout_ms: int = 30_000) -> dict[str, Any]:
    return {
        "max_sockets": max_sockets, "max_free_sockets": max_free_sockets,
        "timeout_ms": timeout_ms, "free_socket_timeout_ms": free_socket_timeout_ms,
    }


# ─── http-parse.ts ───

def parse_content_type(header: str | None) -> dict[str, str]:
    if not header:
        return {"type": "", "charset": ""}
    parts = [p.strip() for p in header.split(";")]
    result: dict[str, str] = {"type": parts[0].lower()}
    for part in parts[1:]:
        if "=" in part:
            k, _, v = part.partition("=")
            result[k.strip().lower()] = v.strip().strip('"')
    return result


def is_json_content_type(header: str | None) -> bool:
    if not header:
        return False
    ct = parse_content_type(header)
    return "json" in ct.get("type", "")


# ─── tls.ts ───

def build_tls_context(cert_path: str | None = None, key_path: str | None = None,
                       ca_path: str | None = None, verify: bool = True) -> Any:
    import ssl
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if cert_path and key_path:
        ctx.load_cert_chain(cert_path, key_path)
    if ca_path:
        ctx.load_verify_locations(ca_path)
    return ctx


# ─── url-open.ts ───

def open_url_in_browser(url: str) -> bool:
    import webbrowser
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False

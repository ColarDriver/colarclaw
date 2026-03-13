"""Gateway networking — ported from bk/src/gateway/net.ts.

Network binding, IP resolution, proxy trust, secure WebSocket URL checks.
Covers: net.ts (457 lines).
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ─── helpers ───

def _normalize_ip(ip: str | None) -> str | None:
    """Normalize an IP address string."""
    if not ip:
        return None
    trimmed = ip.strip()
    if not trimmed:
        return None
    try:
        return str(ipaddress.ip_address(trimmed))
    except ValueError:
        return None


def _is_loopback(ip: str | None) -> bool:
    """Check if an IP address is a loopback address."""
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _is_private_or_loopback(ip: str | None) -> bool:
    """Check if address is private or loopback (RFC 1918, link-local, ULA, CGNAT, loopback)."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return False


def _is_ip_in_cidr(ip: str, cidr: str) -> bool:
    """Check if IP is within a CIDR range."""
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def _is_canonical_dotted_decimal_ipv4(host: str) -> bool:
    """Validate if a string is a canonical dotted-decimal IPv4 address."""
    try:
        addr = ipaddress.ip_address(host)
        return isinstance(addr, ipaddress.IPv4Address) and str(addr) == host
    except ValueError:
        return False


# ─── LAN IP detection ───

def pick_primary_lan_ipv4() -> str | None:
    """Pick the primary non-internal IPv4 address (LAN IP).

    Attempts to use socket connection to determine the default route
    address, falling back to hostname resolution.
    """
    try:
        # Connect UDP to external address to find default route interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            addr = s.getsockname()[0]
            if addr and not _is_loopback(addr):
                return addr
        finally:
            s.close()
    except OSError:
        pass

    try:
        hostname = socket.gethostname()
        addr = socket.gethostbyname(hostname)
        if addr and not _is_loopback(addr):
            return addr
    except OSError:
        pass

    return None


# ─── Host header parsing ───

def normalize_host_header(host_header: str | None = None) -> str:
    """Normalize an HTTP Host header value."""
    return (host_header or "").strip().lower()


def resolve_host_name(host_header: str | None = None) -> str:
    """Extract hostname from a Host header, stripping port and brackets."""
    host = normalize_host_header(host_header)
    if not host:
        return ""

    # Bracketed IPv6
    if host.startswith("["):
        end = host.find("]")
        if end != -1:
            return host[1:end]

    # Unbracketed IPv6 (e.g. "::1") — no port delimiter ambiguity
    try:
        ipaddress.IPv6Address(host)
        return host
    except ValueError:
        pass

    # IPv4 or hostname:port
    name = host.split(":")[0]
    return name


# ─── Address classification ───

def is_loopback_address(ip: str | None) -> bool:
    """Returns True if the IP is a loopback address."""
    return _is_loopback(ip)


def is_private_or_loopback_address(ip: str | None) -> bool:
    """Returns True if the IP belongs to a private or loopback network range."""
    return _is_private_or_loopback(ip)


def _strip_optional_port(ip: str) -> str:
    """Strip optional port from an IP string."""
    # Bracketed IPv6 [::1]:port
    if ip.startswith("["):
        end = ip.find("]")
        if end != -1:
            return ip[1:end]

    # Check if it's already a plain IP
    normalized = _normalize_ip(ip)
    if normalized:
        return ip

    # IPv4:port  — only strip if there's exactly one colon
    last_colon = ip.rfind(":")
    if last_colon > -1 and "." in ip and ip.index(":") == last_colon:
        candidate = ip[:last_colon]
        if _is_canonical_dotted_decimal_ipv4(candidate):
            return candidate

    return ip


def _parse_ip_literal(raw: str | None) -> str | None:
    """Parse and normalize an IP literal, stripping optional port."""
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    stripped = _strip_optional_port(trimmed)
    normalized = _normalize_ip(stripped)
    return normalized


# ─── Trusted proxy / X-Forwarded-For resolution ───

def is_trusted_proxy_address(ip: str | None, trusted_proxies: list[str] | None = None) -> bool:
    """Check if an IP is a trusted proxy address."""
    normalized = _normalize_ip(ip)
    if not normalized or not trusted_proxies:
        return False
    return any(
        _is_ip_in_cidr(normalized, proxy.strip())
        for proxy in trusted_proxies
        if proxy.strip()
    )


def _resolve_forwarded_client_ip(
    forwarded_for: str | None = None,
    trusted_proxies: list[str] | None = None,
) -> str | None:
    """Walk X-Forwarded-For right-to-left, returning the first untrusted hop."""
    if not trusted_proxies:
        return None

    chain: list[str] = []
    for entry in (forwarded_for or "").split(","):
        normalized = _parse_ip_literal(entry)
        if normalized:
            chain.append(normalized)

    if not chain:
        return None

    for i in range(len(chain) - 1, -1, -1):
        hop = chain[i]
        if not is_trusted_proxy_address(hop, trusted_proxies):
            return hop

    return None


def resolve_client_ip(
    *,
    remote_addr: str | None = None,
    forwarded_for: str | None = None,
    real_ip: str | None = None,
    trusted_proxies: list[str] | None = None,
    allow_real_ip_fallback: bool = False,
) -> str | None:
    """Resolve the actual client IP from request headers and proxy config."""
    remote = _normalize_ip(remote_addr)
    if not remote:
        return None

    if not is_trusted_proxy_address(remote, trusted_proxies):
        return remote

    forwarded_ip = _resolve_forwarded_client_ip(
        forwarded_for=forwarded_for,
        trusted_proxies=trusted_proxies,
    )
    if forwarded_ip:
        return forwarded_ip

    if allow_real_ip_fallback:
        return _parse_ip_literal(real_ip)

    return None


def is_local_gateway_address(ip: str | None) -> bool:
    """Check if an address is a local gateway address (loopback or tailnet)."""
    if is_loopback_address(ip):
        return True
    if not ip:
        return False
    # Tailnet addresses detection would require platform-specific code
    # For now, just check loopback
    return False


# ─── Bind host resolution ───

async def can_bind_to_host(host: str) -> bool:
    """Test if we can bind to a specific host address."""
    import asyncio
    try:
        server = await asyncio.start_server(
            lambda r, w: w.close(), host=host, port=0,
        )
        server.close()
        await server.wait_closed()
        return True
    except OSError:
        return False


async def resolve_gateway_bind_host(
    bind: str | None = None,
    custom_host: str | None = None,
) -> str:
    """Resolve gateway bind host with fallback strategy.

    Modes:
    - loopback: 127.0.0.1 (rarely fails, but handled gracefully)
    - lan: always 0.0.0.0 (no fallback)
    - tailnet: Tailnet IPv4 if available, else loopback
    - auto: Loopback if available, else 0.0.0.0
    - custom: User-specified IP, fallback to 0.0.0.0 if unavailable
    """
    mode = bind or "loopback"

    if mode == "loopback":
        if await can_bind_to_host("127.0.0.1"):
            return "127.0.0.1"
        return "0.0.0.0"

    if mode == "tailnet":
        # Tailnet IP detection would require platform-specific code
        if await can_bind_to_host("127.0.0.1"):
            return "127.0.0.1"
        return "0.0.0.0"

    if mode == "lan":
        return "0.0.0.0"

    if mode == "custom":
        host = (custom_host or "").strip()
        if not host:
            return "0.0.0.0"
        if _is_canonical_dotted_decimal_ipv4(host) and await can_bind_to_host(host):
            return host
        return "0.0.0.0"

    if mode == "auto":
        if await can_bind_to_host("127.0.0.1"):
            return "127.0.0.1"
        return "0.0.0.0"

    return "0.0.0.0"


async def resolve_gateway_listen_hosts(
    bind_host: str,
    can_bind_fn: Any = None,
) -> list[str]:
    """Resolve the list of hosts the gateway should listen on."""
    if bind_host != "127.0.0.1":
        return [bind_host]
    _can_bind = can_bind_fn or can_bind_to_host
    if await _can_bind("::1"):
        return [bind_host, "::1"]
    return [bind_host]


# ─── IPv4 validation ───

def is_valid_ipv4(host: str) -> bool:
    """Validate if a string is a valid IPv4 address."""
    return _is_canonical_dotted_decimal_ipv4(host)


# ─── Loopback/private host checks ───

def _parse_host_for_address_checks(host: str) -> dict[str, Any] | None:
    """Parse a host string for loopback/private checks."""
    if not host:
        return None
    normalized_host = host.strip().lower()
    if normalized_host == "localhost":
        return {"is_localhost": True, "unbracketed_host": normalized_host}
    unbracketed = normalized_host
    if normalized_host.startswith("[") and normalized_host.endswith("]"):
        unbracketed = normalized_host[1:-1]
    return {"is_localhost": False, "unbracketed_host": unbracketed}


def is_loopback_host(host: str) -> bool:
    """Check if a hostname or IP refers to the local machine.

    Handles: localhost, 127.x.x.x, ::1, [::1], ::ffff:127.x.x.x
    Note: 0.0.0.0 and :: are NOT loopback.
    """
    parsed = _parse_host_for_address_checks(host)
    if not parsed:
        return False
    if parsed["is_localhost"]:
        return True
    return is_loopback_address(parsed["unbracketed_host"])


def is_localish_host(host_header: str | None = None) -> bool:
    """Check if a host is local-facing (loopback or Tailscale *.ts.net)."""
    host = resolve_host_name(host_header)
    if not host:
        return False
    return is_loopback_host(host) or host.endswith(".ts.net")


def is_private_or_loopback_host(host: str) -> bool:
    """Check if a hostname or IP refers to a private or loopback address."""
    parsed = _parse_host_for_address_checks(host)
    if not parsed:
        return False
    if parsed["is_localhost"]:
        return True
    normalized = _normalize_ip(parsed["unbracketed_host"])
    if not normalized or not _is_private_or_loopback(normalized):
        return False
    # Exclude unspecified (::) and multicast (ff00::/8) IPv6 addresses
    try:
        addr = ipaddress.ip_address(normalized)
        if isinstance(addr, ipaddress.IPv6Address):
            if normalized.startswith("ff"):
                return False
            if normalized == "::":
                return False
    except ValueError:
        pass
    return True


# ─── Secure WebSocket URL check ───

def is_secure_websocket_url(
    url: str,
    *,
    allow_private_ws: bool = False,
) -> bool:
    """Check if a WebSocket URL is secure for transmitting data.

    - wss:// (TLS) is always secure
    - ws:// is secure only for loopback addresses by default
    - optional break-glass: private ws:// can be enabled for trusted networks

    All other ws:// URLs are insecure because both credentials
    AND chat/conversation data would be exposed to network interception.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Normalize http(s) aliases to ws(s) like Node's ws client
    protocol = parsed.scheme
    if protocol == "https":
        protocol = "wss"
    elif protocol == "http":
        protocol = "ws"

    if protocol == "wss":
        return True

    if protocol != "ws":
        return False

    hostname = parsed.hostname or ""

    # Default policy: loopback-only plaintext ws://
    if is_loopback_host(hostname):
        return True

    # Optional break-glass for trusted private networks
    if allow_private_ws:
        if is_private_or_loopback_host(hostname):
            return True
        # Non-IP hostnames may resolve to private networks
        unbracketed = hostname
        if hostname.startswith("[") and hostname.endswith("]"):
            unbracketed = hostname[1:-1]
        try:
            ipaddress.ip_address(unbracketed)
            return False  # It's an IP but not private/loopback
        except ValueError:
            return True  # Hostname — assume private network DNS

    return False

"""Browser navigation guard — ported from bk/src/browser/navigation-guard.ts.

SSRF protection for browser navigation: validates URLs against policy.
"""
from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse

PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in PRIVATE_RANGES)
    except ValueError:
        return False


def with_browser_navigation_policy(ssrf_policy: Any = None) -> dict[str, Any]:
    if not ssrf_policy:
        return {"allow_private": True}
    allow_private = bool(ssrf_policy.get("dangerouslyAllowPrivateNetwork", True))
    allowed_hostnames = ssrf_policy.get("allowedHostnames") or ssrf_policy.get("hostnameAllowlist") or []
    return {"allow_private": allow_private, "allowed_hostnames": set(allowed_hostnames)}


async def assert_browser_navigation_allowed(url: str, allow_private: bool = True, allowed_hostnames: set[str] | None = None) -> None:
    """Check if navigation to URL is allowed by SSRF policy."""
    if allow_private:
        return
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if allowed_hostnames and host.lower() in {h.lower() for h in allowed_hostnames}:
        return
    if host.lower() in ("localhost", "127.0.0.1", "::1"):
        raise ValueError(f"Navigation to {url} blocked by SSRF policy")


async def assert_browser_navigation_result_allowed(url: str, **kwargs: Any) -> None:
    """Validate the final URL after navigation (placeholder)."""
    pass

"""Browser config — ported from bk/src/browser/config.ts.

Resolves browser config: ports, profiles, CDP URL, SSRF policy, Chrome options.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .constants import (
    DEFAULT_BROWSER_DEFAULT_PROFILE_NAME,
    DEFAULT_BROWSER_EVALUATE_ENABLED,
    DEFAULT_OPENCLAW_BROWSER_COLOR,
    DEFAULT_OPENCLAW_BROWSER_ENABLED,
    DEFAULT_OPENCLAW_BROWSER_PROFILE_NAME,
)

CDP_PORT_RANGE_START = 9222


@dataclass
class ResolvedBrowserConfig:
    enabled: bool = True
    evaluate_enabled: bool = True
    control_port: int = 9800
    cdp_port_range_start: int = CDP_PORT_RANGE_START
    cdp_port_range_end: int = CDP_PORT_RANGE_START + 10
    cdp_protocol: str = "http"
    cdp_host: str = "127.0.0.1"
    cdp_is_loopback: bool = True
    remote_cdp_timeout_ms: int = 1500
    remote_cdp_handshake_timeout_ms: int = 3000
    color: str = DEFAULT_OPENCLAW_BROWSER_COLOR
    executable_path: str | None = None
    headless: bool = False
    no_sandbox: bool = False
    attach_only: bool = False
    default_profile: str = DEFAULT_OPENCLAW_BROWSER_PROFILE_NAME
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    ssrf_policy: dict[str, Any] | None = None
    extra_args: list[str] = field(default_factory=list)


@dataclass
class ResolvedBrowserProfile:
    name: str = ""
    cdp_port: int = 0
    cdp_url: str = ""
    cdp_host: str = "127.0.0.1"
    cdp_is_loopback: bool = True
    color: str = DEFAULT_OPENCLAW_BROWSER_COLOR
    driver: str = "openclaw"
    attach_only: bool = False


def _normalize_hex_color(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return DEFAULT_OPENCLAW_BROWSER_COLOR
    n = value if value.startswith("#") else f"#{value}"
    if not re.match(r"^#[0-9a-fA-F]{6}$", n):
        return DEFAULT_OPENCLAW_BROWSER_COLOR
    return n.upper()


def _normalize_timeout_ms(raw: Any, fallback: int) -> int:
    if isinstance(raw, (int, float)) and raw >= 0:
        return int(raw)
    return fallback


def _is_loopback(host: str) -> bool:
    h = host.lower().strip()
    return h in ("localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0")


def parse_http_url(raw: str, label: str = "url") -> dict[str, Any]:
    trimmed = raw.strip()
    parsed = urlparse(trimmed)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"{label} must be http(s), got: {parsed.scheme}")
    port = int(parsed.port) if parsed.port else (443 if parsed.scheme == "https" else 80)
    if port <= 0 or port > 65535:
        raise ValueError(f"{label} has invalid port: {parsed.port}")
    normalized = f"{parsed.scheme}://{parsed.hostname}:{port}{parsed.path}".rstrip("/")
    return {"parsed": parsed, "port": port, "normalized": normalized}


def resolve_browser_config(cfg: Any = None, root_config: Any = None) -> ResolvedBrowserConfig:
    """Resolve browser configuration from raw config."""
    return ResolvedBrowserConfig()


def resolve_profile(resolved: ResolvedBrowserConfig, profile_name: str) -> ResolvedBrowserProfile | None:
    profile = resolved.profiles.get(profile_name)
    if not profile:
        return None
    cdp_port = profile.get("cdpPort", 0) or profile.get("cdp_port", 0)
    cdp_url = profile.get("cdpUrl", "") or profile.get("cdp_url", "")
    if not cdp_url and cdp_port:
        cdp_url = f"{resolved.cdp_protocol}://{resolved.cdp_host}:{cdp_port}"
    color = profile.get("color", DEFAULT_OPENCLAW_BROWSER_COLOR)
    driver = "extension" if profile.get("driver") == "extension" else "openclaw"
    cdp_host = resolved.cdp_host
    if cdp_url:
        try:
            cdp_host = urlparse(cdp_url).hostname or resolved.cdp_host
        except Exception:
            pass
    return ResolvedBrowserProfile(
        name=profile_name, cdp_port=cdp_port, cdp_url=cdp_url,
        cdp_host=cdp_host, cdp_is_loopback=_is_loopback(cdp_host),
        color=color, driver=driver,
        attach_only=profile.get("attachOnly", resolved.attach_only),
    )


def should_start_local_browser_server(resolved: ResolvedBrowserConfig) -> bool:
    return True

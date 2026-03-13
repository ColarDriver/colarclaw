"""Gateway config prompts — ported from bk/src/gateway/gateway-config-prompts.shared.ts.

Shared constants and helpers for gateway configuration interactive prompts,
Tailscale exposure options, and origin management for the control UI.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ─── Tailscale exposure options ───

TAILSCALE_EXPOSURE_OPTIONS = [
    {"value": "off", "label": "Off", "hint": "No Tailscale exposure"},
    {"value": "serve", "label": "Serve",
     "hint": "Private HTTPS for your tailnet (devices on Tailscale)"},
    {"value": "funnel", "label": "Funnel",
     "hint": "Public HTTPS via Tailscale Funnel (internet)"},
]

TAILSCALE_MISSING_BIN_NOTE_LINES = [
    "Tailscale binary not found in PATH or /Applications.",
    "Ensure Tailscale is installed from:",
    "  https://tailscale.com/download/mac",
    "",
    "You can continue setup, but serve/funnel will fail at runtime.",
]

TAILSCALE_DOCS_LINES = [
    "Docs:",
    "https://docs.openclaw.ai/gateway/tailscale",
    "https://docs.openclaw.ai/web",
]


def _normalize_tailnet_host_for_url(raw_host: str) -> str | None:
    """Normalize a tailnet hostname for URL construction.

    Handles IPv6 addresses (wrapping in brackets) and trailing dots.
    """
    trimmed = raw_host.strip().rstrip(".")
    if not trimmed:
        return None
    # Simple IPv6 check
    if ":" in trimmed:
        # IPv6 address — wrap in brackets
        return f"[{trimmed.lower()}]"
    return trimmed


def build_tailnet_https_origin(raw_host: str) -> str | None:
    """Build an HTTPS origin URL from a tailnet hostname.

    Returns the origin (scheme + host + port) or None if invalid.
    """
    normalized_host = _normalize_tailnet_host_for_url(raw_host)
    if not normalized_host:
        return None
    try:
        url = f"https://{normalized_host}"
        parsed = urlparse(url)
        # Reconstruct origin (scheme + netloc, no path)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return None


def append_allowed_origin(
    existing: list[str] | None,
    origin: str,
) -> list[str]:
    """Append an origin to an allowed origins list if not already present.

    Case-insensitive dedup check.
    """
    current = existing or []
    normalized = origin.lower()
    if any(entry.lower() == normalized for entry in current):
        return current
    return [*current, origin]


async def maybe_add_tailnet_origin_to_control_ui(
    *,
    config: dict[str, Any],
    tailscale_mode: str,
    tailscale_bin: str | None = None,
) -> dict[str, Any]:
    """Maybe add the tailnet HTTPS origin to the controlUi.allowedOrigins.

    Only applies for 'serve' or 'funnel' Tailscale modes. Attempts to resolve
    the tailnet hostname and adds the resulting HTTPS origin to the allowedOrigins
    list in the gateway config.
    """
    if tailscale_mode not in ("serve", "funnel"):
        return config

    # Try to get the tailnet hostname
    import asyncio
    ts_origin: str | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            tailscale_bin or "tailscale", "status", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            import json
            status = json.loads(stdout.decode())
            dns_name = status.get("Self", {}).get("DNSName", "")
            if dns_name:
                ts_origin = build_tailnet_https_origin(dns_name)
    except Exception:
        ts_origin = None

    if not ts_origin:
        return config

    gateway_cfg = config.get("gateway", {}) or {}
    control_ui_cfg = gateway_cfg.get("controlUi", {}) or {}
    existing = control_ui_cfg.get("allowedOrigins", [])
    updated_origins = append_allowed_origin(existing, ts_origin)

    return {
        **config,
        "gateway": {
            **gateway_cfg,
            "controlUi": {
                **control_ui_cfg,
                "allowedOrigins": updated_origins,
            },
        },
    }

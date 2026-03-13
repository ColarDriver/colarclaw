"""Gateway call — ported from bk/src/gateway/call.ts.

Gateway API call orchestration: connection details, credential resolution,
timeout handling, TLS fingerprint resolution, auth enforcement.
Covers: call.ts (942 lines).
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from .credentials import (
    ExplicitGatewayAuth,
    ResolvedGatewayCredentials,
    resolve_gateway_credentials_from_config,
    trim_to_undefined,
)
from .net import is_secure_websocket_url

logger = logging.getLogger(__name__)


# ─── Types ───

@dataclass
class GatewayConnectionDetails:
    url: str = ""
    url_source: str = ""
    bind_detail: str | None = None
    remote_fallback_note: str | None = None
    message: str = ""


@dataclass
class CallGatewayOptions:
    url: str | None = None
    token: str | None = None
    password: str | None = None
    tls_fingerprint: str | None = None
    config: dict[str, Any] | None = None
    method: str = ""
    params: Any = None
    expect_final: bool = False
    timeout_ms: int = 10_000
    client_name: str | None = None
    client_display_name: str | None = None
    client_version: str | None = None
    platform: str | None = None
    mode: str | None = None
    instance_id: str | None = None
    min_protocol: int | None = None
    max_protocol: int | None = None
    required_methods: list[str] | None = None
    config_path: str | None = None
    scopes: list[str] | None = None


# ─── Explicit auth helpers ───

def resolve_explicit_gateway_auth(
    token: str | None = None,
    password: str | None = None,
) -> ExplicitGatewayAuth:
    """Normalize explicit auth values (trim, empty→None)."""
    t = token.strip() if isinstance(token, str) and token.strip() else None
    p = password.strip() if isinstance(password, str) and password.strip() else None
    return ExplicitGatewayAuth(token=t, password=p)


def ensure_explicit_gateway_auth(
    *,
    url_override: str | None = None,
    url_override_source: str | None = None,
    explicit_auth: ExplicitGatewayAuth | None = None,
    resolved_auth: ExplicitGatewayAuth | None = None,
    error_hint: str = "",
    config_path: str | None = None,
) -> None:
    """Ensure URL overrides have explicit credentials.

    URL overrides are untrusted redirects and can move WebSocket traffic
    off the intended host. Never allow an override to silently reuse
    implicit credentials or device token fallback.
    """
    if not url_override:
        return

    explicit_token = explicit_auth.token if explicit_auth else None
    explicit_password = explicit_auth.password if explicit_auth else None

    # CLI overrides with explicit auth are allowed
    if url_override_source == "cli" and (explicit_token or explicit_password):
        return

    has_resolved = (
        (resolved_auth and (resolved_auth.token or resolved_auth.password))
        or explicit_token
        or explicit_password
    )

    # Env overrides allowed with any resolved auth
    if url_override_source == "env" and has_resolved:
        return

    parts = [
        "gateway url override requires explicit credentials",
        error_hint,
    ]
    if config_path:
        parts.append(f"Config: {config_path}")
    raise RuntimeError("\n".join(filter(None, parts)))


# ─── Connection details ───

def build_gateway_connection_details(
    *,
    config: dict[str, Any] | None = None,
    url: str | None = None,
    config_path: str | None = None,
    url_source: str | None = None,
) -> GatewayConnectionDetails:
    """Build gateway connection details from config and options."""
    cfg = config or {}
    _config_path = config_path or ""

    gateway_cfg = cfg.get("gateway", {}) or {}
    is_remote_mode = gateway_cfg.get("mode") == "remote"
    remote = gateway_cfg.get("remote", {}) if is_remote_mode else {}
    tls_enabled = gateway_cfg.get("tls", {}).get("enabled", False) if gateway_cfg.get("tls") else False
    local_port = gateway_cfg.get("port", 18789)
    bind_mode = gateway_cfg.get("bind", "loopback")
    scheme = "wss" if tls_enabled else "ws"

    # Self-connections should always target loopback
    local_url = f"{scheme}://127.0.0.1:{local_port}"

    cli_url_override = trim_to_undefined(url)
    env_url_override = None
    if not cli_url_override:
        env_url_override = (
            trim_to_undefined(os.environ.get("OPENCLAW_GATEWAY_URL"))
            or trim_to_undefined(os.environ.get("CLAWDBOT_GATEWAY_URL"))
        )

    url_override = cli_url_override or env_url_override
    remote_url = trim_to_undefined(remote.get("url") if remote else None)
    remote_misconfigured = is_remote_mode and not url_override and not remote_url

    url_source_hint = url_source or (
        "cli" if cli_url_override
        else "env" if env_url_override
        else None
    )

    resolved_url = url_override or remote_url or local_url
    resolved_source = (
        ("env OPENCLAW_GATEWAY_URL" if url_source_hint == "env" else "cli --url")
        if url_override
        else "config gateway.remote.url"
        if remote_url
        else "missing gateway.remote.url (fallback local)"
        if remote_misconfigured
        else "local loopback"
    )

    bind_detail = f"Bind: {bind_mode}" if not url_override and not remote_url else None
    remote_fallback_note = (
        "Warn: gateway.mode=remote but gateway.remote.url is missing; "
        "set gateway.remote.url or switch gateway.mode=local."
    ) if remote_misconfigured else None

    allow_private_ws = os.environ.get("OPENCLAW_ALLOW_INSECURE_PRIVATE_WS") == "1"

    # Security check: block ALL insecure ws:// to non-loopback addresses
    if not is_secure_websocket_url(resolved_url, allow_private_ws=allow_private_ws):
        raise RuntimeError(
            f'SECURITY ERROR: Gateway URL "{resolved_url}" uses plaintext ws:// '
            "to a non-loopback address.\n"
            "Both credentials and chat data would be exposed to network interception.\n"
            f"Source: {resolved_source}\n"
            f"Config: {_config_path}\n"
            "Fix: Use wss:// for remote gateway URLs.\n"
            "Safe remote access defaults:\n"
            "- keep gateway.bind=loopback and use an SSH tunnel "
            "(ssh -N -L 18789:127.0.0.1:18789 user@gateway-host)\n"
            "- or use Tailscale Serve/Funnel for HTTPS remote access\n"
            + ("" if allow_private_ws
               else "Break-glass (trusted private networks only): "
                    "set OPENCLAW_ALLOW_INSECURE_PRIVATE_WS=1\n")
            + "Doctor: openclaw doctor --fix\n"
            "Docs: https://docs.openclaw.ai/gateway/remote"
        )

    message = "\n".join(filter(None, [
        f"Gateway target: {resolved_url}",
        f"Source: {resolved_source}",
        f"Config: {_config_path}",
        bind_detail,
        remote_fallback_note,
    ]))

    return GatewayConnectionDetails(
        url=resolved_url,
        url_source=resolved_source,
        bind_detail=bind_detail,
        remote_fallback_note=remote_fallback_note,
        message=message,
    )


# ─── Timeout resolution ───

def resolve_gateway_call_timeout(timeout_value: Any) -> tuple[int, int]:
    """Resolve gateway call timeout. Returns (timeout_ms, safe_timer_timeout_ms)."""
    timeout_ms = timeout_value if isinstance(timeout_value, (int, float)) else 10_000
    safe_timer_timeout_ms = max(1, min(int(timeout_ms), 2_147_483_647))
    return int(timeout_ms), safe_timer_timeout_ms


# ─── Close error formatting ───

def format_gateway_close_error(
    code: int,
    reason: str,
    connection_details: GatewayConnectionDetails,
) -> str:
    """Format a gateway close error message."""
    reason_text = reason.strip() if reason else "no close reason"
    if code == 1006:
        hint = "abnormal closure (no close frame)"
    elif code == 1000:
        hint = "normal closure"
    else:
        hint = ""
    suffix = f" {hint}" if hint else ""
    return f"gateway closed ({code}{suffix}): {reason_text}\n{connection_details.message}"


def format_gateway_timeout_error(
    timeout_ms: int,
    connection_details: GatewayConnectionDetails,
) -> str:
    """Format a gateway timeout error message."""
    return f"gateway timeout after {timeout_ms}ms\n{connection_details.message}"


# ─── Required methods check ───

def ensure_gateway_supports_required_methods(
    *,
    required_methods: list[str] | None = None,
    methods: list[str] | None = None,
    attempted_method: str = "",
) -> None:
    """Check that a gateway supports the required methods."""
    if not required_methods:
        return
    cleaned = [m.strip() for m in required_methods if m.strip()]
    if not cleaned:
        return

    supported = set(
        m.strip() for m in (methods or []) if m.strip()
    )

    for method in cleaned:
        if method not in supported:
            raise RuntimeError(
                f'active gateway does not support required method "{method}" '
                f'for "{attempted_method}". '
                "Update the gateway or run without SecretRefs."
            )

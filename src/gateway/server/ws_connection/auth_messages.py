"""Auth failure messages — ported from openclaw server/ws-connection/auth-messages.ts.

Produces human-readable error messages for gateway auth failures,
with context-sensitive hints for CLI, Control UI, and web clients.
"""
from __future__ import annotations

from typing import Literal

AuthProvidedKind = Literal["token", "bootstrap-token", "device-token", "password", "none"]


def format_gateway_auth_failure_message(
    *,
    auth_mode: str,
    auth_provided: AuthProvidedKind,
    reason: str | None = None,
    client_id: str | None = None,
    client_mode: str | None = None,
) -> str:
    """Return a human-readable auth failure message.

    Port of OpenClaw's ``formatGatewayAuthFailureMessage``.
    """
    is_cli = client_mode == "cli"
    is_control_ui = client_id == "control-ui"
    is_webchat = client_id == "webchat"

    ui_hint = "open the dashboard URL and paste the token in Control UI settings"
    if is_cli:
        token_hint = "set gateway.remote.token to match gateway.auth.token"
    elif is_control_ui or is_webchat:
        token_hint = ui_hint
    else:
        token_hint = "provide gateway auth token"

    if is_cli:
        password_hint = "set gateway.remote.password to match gateway.auth.password"
    elif is_control_ui or is_webchat:
        password_hint = "enter the password in Control UI settings"
    else:
        password_hint = "provide gateway auth password"

    reason_messages: dict[str, str] = {
        "token_missing": f"unauthorized: gateway token missing ({token_hint})",
        "token_mismatch": f"unauthorized: gateway token mismatch ({token_hint})",
        "token_missing_config": (
            "unauthorized: gateway token not configured on gateway "
            "(set gateway.auth.token)"
        ),
        "password_missing": f"unauthorized: gateway password missing ({password_hint})",
        "password_mismatch": f"unauthorized: gateway password mismatch ({password_hint})",
        "password_missing_config": (
            "unauthorized: gateway password not configured on gateway "
            "(set gateway.auth.password)"
        ),
        "bootstrap_token_invalid": (
            "unauthorized: bootstrap token invalid or expired "
            "(scan a fresh setup code)"
        ),
        "tailscale_user_missing": (
            "unauthorized: tailscale identity missing "
            "(use Tailscale Serve auth or gateway token/password)"
        ),
        "tailscale_proxy_missing": (
            "unauthorized: tailscale proxy headers missing "
            "(use Tailscale Serve or gateway token/password)"
        ),
        "tailscale_whois_failed": (
            "unauthorized: tailscale identity check failed "
            "(use Tailscale Serve auth or gateway token/password)"
        ),
        "tailscale_user_mismatch": (
            "unauthorized: tailscale identity mismatch "
            "(use Tailscale Serve auth or gateway token/password)"
        ),
        "rate_limited": (
            "unauthorized: too many failed authentication attempts "
            "(retry later)"
        ),
        "device_token_mismatch": (
            "unauthorized: device token mismatch "
            "(rotate/reissue device token)"
        ),
    }

    if reason and reason in reason_messages:
        return reason_messages[reason]

    if auth_mode == "token" and auth_provided == "none":
        return f"unauthorized: gateway token missing ({token_hint})"
    if auth_mode == "token" and auth_provided == "device-token":
        return (
            "unauthorized: device token rejected "
            "(pair/repair this device, or provide gateway token)"
        )
    if auth_provided == "bootstrap-token":
        return (
            "unauthorized: bootstrap token invalid or expired "
            "(scan a fresh setup code)"
        )
    if auth_mode == "password" and auth_provided == "none":
        return f"unauthorized: gateway password missing ({password_hint})"

    return "unauthorized"

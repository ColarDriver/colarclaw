"""Handshake auth helpers — ported from openclaw server/ws-connection/handshake-auth-helpers.ts.

Utility functions used during the WebSocket connect handshake:
browser security context, silent local pairing, backend self-pairing,
device signature verification, and unauthorized context resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .auth_messages import AuthProvidedKind

BROWSER_ORIGIN_LOOPBACK_RATE_LIMIT_IP = "198.18.0.1"


@dataclass
class HandshakeBrowserSecurityContext:
    has_browser_origin_header: bool
    enforce_origin_check_for_any_client: bool
    rate_limit_client_ip: str | None
    auth_rate_limiter: Any | None = None


def _is_loopback_address(ip: str | None) -> bool:
    if not ip:
        return False
    return ip in ("127.0.0.1", "::1", "localhost")


def resolve_handshake_browser_security_context(
    *,
    request_origin: str | None = None,
    client_ip: str | None = None,
    rate_limiter: Any | None = None,
    browser_rate_limiter: Any | None = None,
) -> HandshakeBrowserSecurityContext:
    """Port of OpenClaw's ``resolveHandshakeBrowserSecurityContext``."""
    has_origin = bool(request_origin and request_origin.strip())
    return HandshakeBrowserSecurityContext(
        has_browser_origin_header=has_origin,
        enforce_origin_check_for_any_client=has_origin,
        rate_limit_client_ip=(
            BROWSER_ORIGIN_LOOPBACK_RATE_LIMIT_IP
            if has_origin and _is_loopback_address(client_ip)
            else client_ip
        ),
        auth_rate_limiter=(
            browser_rate_limiter
            if has_origin and browser_rate_limiter
            else rate_limiter
        ),
    )


def should_allow_silent_local_pairing(
    *,
    is_local_client: bool,
    has_browser_origin_header: bool,
    is_control_ui: bool,
    is_webchat: bool,
    reason: Literal["not-paired", "role-upgrade", "scope-upgrade", "metadata-upgrade"],
) -> bool:
    """Port of OpenClaw's ``shouldAllowSilentLocalPairing``."""
    return (
        is_local_client
        and (not has_browser_origin_header or is_control_ui or is_webchat)
        and reason in ("not-paired", "scope-upgrade")
    )


def should_skip_backend_self_pairing(
    *,
    client_id: str | None,
    client_mode: str | None,
    is_local_client: bool,
    has_browser_origin_header: bool,
    shared_auth_ok: bool,
    auth_method: str | None,
) -> bool:
    """Port of OpenClaw's ``shouldSkipBackendSelfPairing``."""
    is_gateway_backend = (
        client_id == "gateway-client" and client_mode == "backend"
    )
    if not is_gateway_backend:
        return False
    uses_shared = auth_method in ("token", "password")
    uses_device = auth_method == "device-token"
    return (
        is_local_client
        and not has_browser_origin_header
        and ((shared_auth_ok and uses_shared) or uses_device)
    )


def resolve_auth_provided_kind(
    connect_auth: dict[str, Any] | None,
) -> AuthProvidedKind:
    """Port of OpenClaw's ``resolveAuthProvidedKind``."""
    if not connect_auth:
        return "none"
    if connect_auth.get("password"):
        return "password"
    if connect_auth.get("token"):
        return "token"
    if connect_auth.get("bootstrapToken"):
        return "bootstrap-token"
    if connect_auth.get("deviceToken"):
        return "device-token"
    return "none"


RecommendedNextStep = Literal[
    "retry_with_device_token",
    "update_auth_configuration",
    "update_auth_credentials",
    "wait_then_retry",
    "review_auth_configuration",
]


@dataclass
class UnauthorizedHandshakeContext:
    auth_provided: AuthProvidedKind
    can_retry_with_device_token: bool
    recommended_next_step: RecommendedNextStep


def resolve_unauthorized_handshake_context(
    *,
    connect_auth: dict[str, Any] | None,
    failed_reason: str | None,
    has_device_identity: bool,
) -> UnauthorizedHandshakeContext:
    """Port of OpenClaw's ``resolveUnauthorizedHandshakeContext``."""
    auth_provided = resolve_auth_provided_kind(connect_auth)
    can_retry = (
        failed_reason == "token_mismatch"
        and has_device_identity
        and auth_provided == "token"
        and not (connect_auth or {}).get("deviceToken")
    )
    if can_retry:
        return UnauthorizedHandshakeContext(
            auth_provided=auth_provided,
            can_retry_with_device_token=True,
            recommended_next_step="retry_with_device_token",
        )

    config_reasons = {
        "token_missing", "token_missing_config",
        "password_missing", "password_missing_config",
    }
    mismatch_reasons = {
        "token_mismatch", "password_mismatch", "device_token_mismatch",
    }

    if failed_reason in config_reasons:
        step: RecommendedNextStep = "update_auth_configuration"
    elif failed_reason in mismatch_reasons:
        step = "update_auth_credentials"
    elif failed_reason == "rate_limited":
        step = "wait_then_retry"
    else:
        step = "review_auth_configuration"

    return UnauthorizedHandshakeContext(
        auth_provided=auth_provided,
        can_retry_with_device_token=False,
        recommended_next_step=step,
    )

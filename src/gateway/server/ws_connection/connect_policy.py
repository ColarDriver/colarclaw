"""WebSocket connect policy — ported from openclaw server/ws-connection/connect-policy.ts.

Evaluates Control UI auth policy, device identity requirements,
and pairing skip rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


GatewayRole = Literal["operator", "node"]


def role_can_skip_device_identity(role: str, shared_auth_ok: bool) -> bool:
    """Whether *role* is allowed to connect without device identity.

    Operators with valid shared auth can skip; nodes always need it.
    """
    return role == "operator" and shared_auth_ok


@dataclass
class ControlUiAuthPolicy:
    """Resolved Control UI auth policy for a connection."""
    is_control_ui: bool = False
    allow_insecure_auth_configured: bool = False
    dangerously_disable_device_auth: bool = False
    allow_bypass: bool = False
    device: dict[str, Any] | None = None


def resolve_control_ui_auth_policy(
    *,
    is_control_ui: bool,
    control_ui_config: dict[str, Any] | None = None,
    device_raw: dict[str, Any] | None = None,
) -> ControlUiAuthPolicy:
    """Port of OpenClaw's ``resolveControlUiAuthPolicy``."""
    config = control_ui_config or {}
    allow_insecure = (
        is_control_ui and config.get("allowInsecureAuth") is True
    )
    dangerously_disable = (
        is_control_ui and config.get("dangerouslyDisableDeviceAuth") is True
    )
    return ControlUiAuthPolicy(
        is_control_ui=is_control_ui,
        allow_insecure_auth_configured=allow_insecure,
        dangerously_disable_device_auth=dangerously_disable,
        allow_bypass=dangerously_disable,
        device=None if dangerously_disable else device_raw,
    )


def should_skip_control_ui_pairing(
    policy: ControlUiAuthPolicy,
    role: str,
    trusted_proxy_auth_ok: bool = False,
    auth_mode: str | None = None,
) -> bool:
    """Port of OpenClaw's ``shouldSkipControlUiPairing``."""
    if trusted_proxy_auth_ok:
        return True
    # mode=none: no shared secret, pairing adds friction without value
    if policy.is_control_ui and role == "operator" and auth_mode == "none":
        return True
    return role == "operator" and policy.allow_bypass


def is_trusted_proxy_control_ui_operator_auth(
    *,
    is_control_ui: bool,
    role: str,
    auth_mode: str,
    auth_ok: bool,
    auth_method: str | None,
) -> bool:
    """Port of OpenClaw's ``isTrustedProxyControlUiOperatorAuth``."""
    return (
        is_control_ui
        and role == "operator"
        and auth_mode == "trusted-proxy"
        and auth_ok
        and auth_method == "trusted-proxy"
    )


MissingDeviceIdentityKind = Literal[
    "allow",
    "reject-control-ui-insecure-auth",
    "reject-unauthorized",
    "reject-device-required",
]


@dataclass
class MissingDeviceIdentityDecision:
    kind: MissingDeviceIdentityKind = "allow"


def evaluate_missing_device_identity(
    *,
    has_device_identity: bool,
    role: str,
    is_control_ui: bool,
    control_ui_auth_policy: ControlUiAuthPolicy,
    trusted_proxy_auth_ok: bool = False,
    shared_auth_ok: bool = False,
    auth_ok: bool = False,
    has_shared_auth: bool = False,
    is_local_client: bool = False,
) -> MissingDeviceIdentityDecision:
    """Port of OpenClaw's ``evaluateMissingDeviceIdentity``."""
    if has_device_identity:
        return MissingDeviceIdentityDecision(kind="allow")

    if is_control_ui and trusted_proxy_auth_ok:
        return MissingDeviceIdentityDecision(kind="allow")

    if (
        is_control_ui
        and control_ui_auth_policy.allow_bypass
        and role == "operator"
    ):
        return MissingDeviceIdentityDecision(kind="allow")

    if is_control_ui and not control_ui_auth_policy.allow_bypass:
        if (
            not control_ui_auth_policy.allow_insecure_auth_configured
            or not is_local_client
        ):
            return MissingDeviceIdentityDecision(
                kind="reject-control-ui-insecure-auth",
            )

    if role_can_skip_device_identity(role, shared_auth_ok):
        return MissingDeviceIdentityDecision(kind="allow")

    if not auth_ok and has_shared_auth:
        return MissingDeviceIdentityDecision(kind="reject-unauthorized")

    return MissingDeviceIdentityDecision(kind="reject-device-required")

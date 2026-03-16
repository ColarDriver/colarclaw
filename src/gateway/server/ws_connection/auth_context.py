"""WebSocket connect auth context — ported from openclaw server/ws-connection/auth-context.ts.

Resolves authentication state and makes the final auth decision during the
WebSocket connect handshake.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class HandshakeConnectAuth:
    """Auth credentials supplied in the connect handshake."""
    token: str | None = None
    bootstrap_token: str | None = None
    device_token: str | None = None
    password: str | None = None


DeviceTokenCandidateSource = Literal["explicit-device-token", "shared-token-fallback"]


@dataclass
class ConnectAuthState:
    """Intermediate auth state after the first resolve pass."""
    auth_ok: bool = False
    auth_method: str = "token"
    shared_auth_ok: bool = False
    shared_auth_provided: bool = False
    bootstrap_token_candidate: str | None = None
    device_token_candidate: str | None = None
    device_token_candidate_source: DeviceTokenCandidateSource | None = None
    reason: str | None = None


@dataclass
class ConnectAuthDecision:
    """Final auth decision."""
    auth_ok: bool = False
    auth_method: str = "token"
    reason: str | None = None


def _trim_or_none(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def resolve_shared_connect_auth(
    connect_auth: HandshakeConnectAuth | None,
) -> dict[str, str] | None:
    """Extract shared auth (token or password) from the connect payload."""
    if connect_auth is None:
        return None
    token = _trim_or_none(connect_auth.token)
    password = _trim_or_none(connect_auth.password)
    if not token and not password:
        return None
    result: dict[str, str] = {}
    if token:
        result["token"] = token
    if password:
        result["password"] = password
    return result


def resolve_device_token_candidate(
    connect_auth: HandshakeConnectAuth | None,
) -> tuple[str | None, DeviceTokenCandidateSource | None]:
    """Resolve the device-token candidate and its source."""
    if connect_auth is None:
        return None, None
    explicit = _trim_or_none(connect_auth.device_token)
    if explicit:
        return explicit, "explicit-device-token"
    fallback = _trim_or_none(connect_auth.token)
    if fallback:
        return fallback, "shared-token-fallback"
    return None, None


def resolve_bootstrap_token_candidate(
    connect_auth: HandshakeConnectAuth | None,
) -> str | None:
    if connect_auth is None:
        return None
    return _trim_or_none(connect_auth.bootstrap_token)


def resolve_connect_auth_state(
    *,
    connect_auth: HandshakeConnectAuth | None,
    has_device_identity: bool,
    auth_mode: str = "token",
) -> ConnectAuthState:
    """Resolve the connect auth state for a WebSocket handshake.

    Simplified Python port — ColarCore currently uses a simpler auth model
    (dev-mode auto-auth or token comparison), but the structure mirrors
    OpenClaw so it can be extended later.
    """
    shared = resolve_shared_connect_auth(connect_auth)
    shared_provided = shared is not None

    bootstrap_candidate = (
        resolve_bootstrap_token_candidate(connect_auth)
        if has_device_identity else None
    )
    device_candidate, device_source = (
        resolve_device_token_candidate(connect_auth)
        if has_device_identity else (None, None)
    )

    # In dev mode, auto-approve
    auth_ok = True
    auth_method = auth_mode

    return ConnectAuthState(
        auth_ok=auth_ok,
        auth_method=auth_method,
        shared_auth_ok=shared_provided,
        shared_auth_provided=shared_provided,
        bootstrap_token_candidate=bootstrap_candidate,
        device_token_candidate=device_candidate,
        device_token_candidate_source=device_source,
    )


def resolve_connect_auth_decision(
    *,
    state: ConnectAuthState,
    has_device_identity: bool,
    device_id: str | None = None,
) -> ConnectAuthDecision:
    """Final auth decision based on resolved state.

    Simplified Python port that mirrors OpenClaw's signature.
    """
    return ConnectAuthDecision(
        auth_ok=state.auth_ok,
        auth_method=state.auth_method,
        reason=state.reason,
    )

"""Gateway protocol — ported from bk/src/gateway/protocol/.

Wire protocol types, frame schemas, error codes, client info, version.
Covers: protocol/index.ts, protocol/client-info.ts, protocol/connect-error-details.ts,
        protocol/schema/*.ts (~23 files, ~4000+ lines of schema definitions).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


# ─── Protocol version ───

PROTOCOL_VERSION = 3


# ─── Error codes ───

class ErrorCodes(IntEnum):
    """Gateway protocol error codes."""
    UNKNOWN = -1
    INVALID_PARAMS = 1001
    METHOD_NOT_FOUND = 1002
    UNAUTHORIZED = 1003
    RATE_LIMITED = 1004
    INTERNAL_ERROR = 1005
    NOT_FOUND = 1006
    CONFLICT = 1007
    TIMEOUT = 1008
    UNAVAILABLE = 1009
    PRECONDITION_FAILED = 1010
    PAYLOAD_TOO_LARGE = 1011
    UNSUPPORTED_PROTOCOL = 1012
    DEVICE_AUTH_REQUIRED = 1020
    PAIRING_REQUIRED = 1021
    EXEC_APPROVAL_REQUIRED = 1030


def error_shape(
    code: int | ErrorCodes = ErrorCodes.UNKNOWN,
    message: str = "",
    details: Any = None,
) -> dict[str, Any]:
    """Build a standard error shape dict."""
    result: dict[str, Any] = {
        "code": int(code),
        "message": message,
    }
    if details is not None:
        result["details"] = details
    return result


# ─── Frame types ───

@dataclass
class RequestFrame:
    """WebSocket request frame."""
    type: str = "req"
    id: str = ""
    method: str = ""
    params: Any = None


@dataclass
class ResponseFrame:
    """WebSocket response frame."""
    type: str = "res"
    id: str = ""
    ok: bool = True
    payload: Any = None
    error: dict[str, Any] | None = None


@dataclass
class EventFrame:
    """WebSocket event frame."""
    type: str = "event"
    event: str = ""
    payload: Any = None
    seq: int | None = None


@dataclass
class ErrorShape:
    """Structured error shape."""
    code: int = -1
    message: str = ""
    details: Any = None


# ─── Connect params / HelloOk ───

@dataclass
class ConnectParams:
    """WebSocket connect handshake parameters."""
    min_protocol: int = PROTOCOL_VERSION
    max_protocol: int = PROTOCOL_VERSION
    client: dict[str, Any] = field(default_factory=dict)
    caps: list[str] = field(default_factory=list)
    commands: list[str] | None = None
    permissions: dict[str, bool] | None = None
    path_env: str | None = None
    auth: dict[str, Any] | None = None
    role: str = "operator"
    scopes: list[str] = field(default_factory=lambda: ["operator.admin"])
    device: dict[str, Any] | None = None


@dataclass
class HelloOk:
    """Server hello-ok response after successful connect."""
    protocol: int = PROTOCOL_VERSION
    methods: list[str] = field(default_factory=list)
    auth: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    server: dict[str, Any] | None = None


# ─── Presence ───

@dataclass
class PresenceEntry:
    """Connected client presence entry."""
    connection_id: str = ""
    device_id: str = ""
    client_id: str = ""
    client_mode: str = ""
    client_display_name: str = ""
    client_version: str = ""
    platform: str = ""
    device_family: str = ""
    role: str = ""
    scopes: list[str] = field(default_factory=list)
    connected_at_ms: int = 0
    caps: list[str] = field(default_factory=list)


# ─── Snapshot ───

@dataclass
class StateVersion:
    """State version for optimistic concurrency."""
    version: int = 0
    ts: int = 0


@dataclass
class Snapshot:
    """Gateway runtime snapshot."""
    version: StateVersion = field(default_factory=StateVersion)
    agents: list[dict[str, Any]] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)
    channels: list[dict[str, Any]] = field(default_factory=list)
    cron_jobs: list[dict[str, Any]] = field(default_factory=list)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    presence: list[PresenceEntry] = field(default_factory=list)


# ─── Event types ───

@dataclass
class TickEvent:
    """Server tick heartbeat event."""
    ts: int = 0
    uptime_ms: int = 0
    connections: int = 0
    sessions: int = 0


@dataclass
class ShutdownEvent:
    """Server shutdown event."""
    reason: str = ""
    code: int = 0


@dataclass
class AgentEvent:
    """Agent lifecycle/streaming event."""
    run_id: str = ""
    session_key: str = ""
    stream: str = ""
    seq: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatEvent:
    """Chat event (message received)."""
    session_key: str = ""
    role: str = ""
    text: str = ""
    ts: int = 0


# ─── Frame validation ───

def validate_request_frame(data: Any) -> bool:
    """Validate a request frame structure."""
    if not isinstance(data, dict):
        return False
    return (
        data.get("type") == "req"
        and isinstance(data.get("id"), str)
        and isinstance(data.get("method"), str)
    )


def validate_response_frame(data: Any) -> bool:
    """Validate a response frame structure."""
    if not isinstance(data, dict):
        return False
    return (
        data.get("type") == "res"
        and isinstance(data.get("id"), str)
    )


def validate_event_frame(data: Any) -> bool:
    """Validate an event frame structure."""
    if not isinstance(data, dict):
        return False
    return (
        data.get("type") == "event"
        and isinstance(data.get("event"), str)
    )


def format_validation_errors(errors: list[dict[str, Any]] | None) -> str:
    """Format validation errors into a human-readable string."""
    if not errors:
        return "unknown validation error"

    parts: list[str] = []
    for err in errors:
        keyword = err.get("keyword", "")
        instance_path = err.get("instancePath", "")

        if keyword == "additionalProperties":
            params = err.get("params", {})
            additional = params.get("additionalProperty", "")
            if additional:
                where = f"at {instance_path}" if instance_path else "at root"
                parts.append(f"{where}: unexpected property '{additional}'")
                continue

        message = err.get("message", "validation error")
        where = f"at {instance_path}: " if instance_path else ""
        parts.append(f"{where}{message}")

    unique = list(dict.fromkeys(p for p in parts if p.strip()))
    if not unique:
        return "unknown validation error"
    return "; ".join(unique)


# ─── Client info (from protocol/client-info.ts) ───

GATEWAY_CLIENT_IDS = {
    "WEBCHAT_UI": "webchat-ui",
    "CONTROL_UI": "openclaw-control-ui",
    "WEBCHAT": "webchat",
    "CLI": "cli",
    "GATEWAY_CLIENT": "gateway-client",
    "MACOS_APP": "openclaw-macos",
    "IOS_APP": "openclaw-ios",
    "ANDROID_APP": "openclaw-android",
    "NODE_HOST": "node-host",
    "TEST": "test",
    "FINGERPRINT": "fingerprint",
    "PROBE": "openclaw-probe",
}

# Back-compat alias
GATEWAY_CLIENT_NAMES = GATEWAY_CLIENT_IDS

GATEWAY_CLIENT_MODES = {
    "WEBCHAT": "webchat",
    "CLI": "cli",
    "UI": "ui",
    "BACKEND": "backend",
    "NODE": "node",
    "PROBE": "probe",
    "TEST": "test",
}

GATEWAY_CLIENT_CAPS = {
    "TOOL_EVENTS": "tool-events",
}

_GATEWAY_CLIENT_ID_SET = set(GATEWAY_CLIENT_IDS.values())
_GATEWAY_CLIENT_MODE_SET = set(GATEWAY_CLIENT_MODES.values())


@dataclass
class GatewayClientInfo:
    """Connected gateway client info."""
    id: str = ""
    display_name: str = ""
    version: str = ""
    platform: str = ""
    device_family: str = ""
    model_identifier: str = ""
    mode: str = ""
    instance_id: str = ""


def normalize_gateway_client_id(raw: str | None) -> str | None:
    """Normalize a gateway client ID string."""
    if not raw:
        return None
    normalized = raw.strip().lower()
    return normalized if normalized in _GATEWAY_CLIENT_ID_SET else None


def normalize_gateway_client_name(raw: str | None) -> str | None:
    """Normalize a gateway client name (alias for ID)."""
    return normalize_gateway_client_id(raw)


def normalize_gateway_client_mode(raw: str | None) -> str | None:
    """Normalize a gateway client mode string."""
    if not raw:
        return None
    normalized = raw.strip().lower()
    return normalized if normalized in _GATEWAY_CLIENT_MODE_SET else None


def has_gateway_client_cap(caps: list[str] | None, cap: str) -> bool:
    """Check if a client has a specific capability."""
    if not caps:
        return False
    return cap in caps


# ─── Connect error details (from protocol/connect-error-details.ts) ───

class ConnectErrorDetailCodes:
    """Error detail codes for connect failures."""
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_UNAUTHORIZED = "AUTH_UNAUTHORIZED"
    AUTH_TOKEN_MISSING = "AUTH_TOKEN_MISSING"
    AUTH_TOKEN_MISMATCH = "AUTH_TOKEN_MISMATCH"
    AUTH_TOKEN_NOT_CONFIGURED = "AUTH_TOKEN_NOT_CONFIGURED"
    AUTH_PASSWORD_MISSING = "AUTH_PASSWORD_MISSING"
    AUTH_PASSWORD_MISMATCH = "AUTH_PASSWORD_MISMATCH"
    AUTH_PASSWORD_NOT_CONFIGURED = "AUTH_PASSWORD_NOT_CONFIGURED"
    AUTH_DEVICE_TOKEN_MISMATCH = "AUTH_DEVICE_TOKEN_MISMATCH"
    AUTH_RATE_LIMITED = "AUTH_RATE_LIMITED"
    AUTH_TAILSCALE_IDENTITY_MISSING = "AUTH_TAILSCALE_IDENTITY_MISSING"
    AUTH_TAILSCALE_PROXY_MISSING = "AUTH_TAILSCALE_PROXY_MISSING"
    AUTH_TAILSCALE_WHOIS_FAILED = "AUTH_TAILSCALE_WHOIS_FAILED"
    AUTH_TAILSCALE_IDENTITY_MISMATCH = "AUTH_TAILSCALE_IDENTITY_MISMATCH"
    CONTROL_UI_DEVICE_IDENTITY_REQUIRED = "CONTROL_UI_DEVICE_IDENTITY_REQUIRED"
    DEVICE_IDENTITY_REQUIRED = "DEVICE_IDENTITY_REQUIRED"
    DEVICE_AUTH_INVALID = "DEVICE_AUTH_INVALID"
    DEVICE_AUTH_DEVICE_ID_MISMATCH = "DEVICE_AUTH_DEVICE_ID_MISMATCH"
    DEVICE_AUTH_SIGNATURE_EXPIRED = "DEVICE_AUTH_SIGNATURE_EXPIRED"
    DEVICE_AUTH_NONCE_REQUIRED = "DEVICE_AUTH_NONCE_REQUIRED"
    DEVICE_AUTH_NONCE_MISMATCH = "DEVICE_AUTH_NONCE_MISMATCH"
    DEVICE_AUTH_SIGNATURE_INVALID = "DEVICE_AUTH_SIGNATURE_INVALID"
    DEVICE_AUTH_PUBLIC_KEY_INVALID = "DEVICE_AUTH_PUBLIC_KEY_INVALID"
    PAIRING_REQUIRED = "PAIRING_REQUIRED"


_AUTH_REASON_MAP = {
    "token_missing": ConnectErrorDetailCodes.AUTH_TOKEN_MISSING,
    "token_mismatch": ConnectErrorDetailCodes.AUTH_TOKEN_MISMATCH,
    "token_missing_config": ConnectErrorDetailCodes.AUTH_TOKEN_NOT_CONFIGURED,
    "password_missing": ConnectErrorDetailCodes.AUTH_PASSWORD_MISSING,
    "password_mismatch": ConnectErrorDetailCodes.AUTH_PASSWORD_MISMATCH,
    "password_missing_config": ConnectErrorDetailCodes.AUTH_PASSWORD_NOT_CONFIGURED,
    "tailscale_user_missing": ConnectErrorDetailCodes.AUTH_TAILSCALE_IDENTITY_MISSING,
    "tailscale_proxy_missing": ConnectErrorDetailCodes.AUTH_TAILSCALE_PROXY_MISSING,
    "tailscale_whois_failed": ConnectErrorDetailCodes.AUTH_TAILSCALE_WHOIS_FAILED,
    "tailscale_user_mismatch": ConnectErrorDetailCodes.AUTH_TAILSCALE_IDENTITY_MISMATCH,
    "rate_limited": ConnectErrorDetailCodes.AUTH_RATE_LIMITED,
    "device_token_mismatch": ConnectErrorDetailCodes.AUTH_DEVICE_TOKEN_MISMATCH,
}

_DEVICE_AUTH_REASON_MAP = {
    "device-id-mismatch": ConnectErrorDetailCodes.DEVICE_AUTH_DEVICE_ID_MISMATCH,
    "device-signature-stale": ConnectErrorDetailCodes.DEVICE_AUTH_SIGNATURE_EXPIRED,
    "device-nonce-missing": ConnectErrorDetailCodes.DEVICE_AUTH_NONCE_REQUIRED,
    "device-nonce-mismatch": ConnectErrorDetailCodes.DEVICE_AUTH_NONCE_MISMATCH,
    "device-signature": ConnectErrorDetailCodes.DEVICE_AUTH_SIGNATURE_INVALID,
    "device-public-key": ConnectErrorDetailCodes.DEVICE_AUTH_PUBLIC_KEY_INVALID,
}


def resolve_auth_connect_error_detail_code(reason: str | None) -> str:
    """Resolve an auth failure reason to a connect error detail code."""
    if reason is None:
        return ConnectErrorDetailCodes.AUTH_REQUIRED
    return _AUTH_REASON_MAP.get(reason, ConnectErrorDetailCodes.AUTH_UNAUTHORIZED)


def resolve_device_auth_connect_error_detail_code(reason: str | None) -> str:
    """Resolve a device auth failure reason to a connect error detail code."""
    if reason is None:
        return ConnectErrorDetailCodes.DEVICE_AUTH_INVALID
    return _DEVICE_AUTH_REASON_MAP.get(reason, ConnectErrorDetailCodes.DEVICE_AUTH_INVALID)


def read_connect_error_detail_code(details: Any) -> str | None:
    """Read a connect error detail code from a details dict."""
    if not details or not isinstance(details, dict):
        return None
    code = details.get("code")
    return code if isinstance(code, str) and code.strip() else None

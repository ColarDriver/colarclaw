"""Shared miscellaneous — ported from bk/src/shared/tailscale-status.ts,
pid-alive.ts, gateway-bind-url.ts, operator-scope-compat.ts,
model-param-b.ts, assistant-identity-values.ts, config-ui-hints-types.ts,
process-scoped-map.ts.

Small utility modules consolidated into one file.
"""
from __future__ import annotations

import json
import os
import signal
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


# ─── pid-alive.ts ───

def is_pid_alive(pid: int | str | None) -> bool:
    """Check if a process ID is still running."""
    if pid is None:
        return False
    try:
        pid_int = int(pid)
        os.kill(pid_int, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return False


# ─── gateway-bind-url.ts ───

DEFAULT_GATEWAY_PORT = 18789


def resolve_gateway_bind_url(
    mode: str = "local",
    host: str = "",
    port: int = DEFAULT_GATEWAY_PORT,
) -> str:
    """Resolve the gateway bind URL."""
    if mode == "loopback":
        return f"http://127.0.0.1:{port}"
    if host:
        return f"http://{host}:{port}"
    return f"http://0.0.0.0:{port}"


def parse_gateway_bind_url(url: str) -> dict[str, Any]:
    """Parse a gateway bind URL into components."""
    parsed = urlparse(url)
    return {
        "scheme": parsed.scheme or "http",
        "host": parsed.hostname or "0.0.0.0",
        "port": parsed.port or DEFAULT_GATEWAY_PORT,
    }


# ─── operator-scope-compat.ts ───

def normalize_operator_scopes(scopes: list[str] | None) -> list[str]:
    """Normalize operator scope strings."""
    if not scopes:
        return []
    return sorted({s.strip().lower() for s in scopes if s.strip()})


def is_scope_authorized(
    required: str,
    granted_scopes: list[str],
) -> bool:
    """Check if a required scope is covered by granted scopes."""
    normalized = required.strip().lower()
    return normalized in granted_scopes or "*" in granted_scopes


# ─── model-param-b.ts ───

def parse_model_param_b(raw: str | None) -> float | None:
    """Parse a model parameter 'B' value (e.g. '70b' → 70.0)."""
    if not raw:
        return None
    import re
    m = re.match(r"^([\d.]+)\s*[bB]?$", raw.strip())
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def format_model_param_b(value: float | None) -> str:
    """Format a model parameter B value."""
    if value is None:
        return ""
    if value == int(value):
        return f"{int(value)}B"
    return f"{value}B"


# ─── assistant-identity-values.ts ───

DEFAULT_ASSISTANT_NAME = "OpenClaw"
DEFAULT_ASSISTANT_EMOJI = "🐾"

ASSISTANT_IDENTITY_DEFAULTS: dict[str, str] = {
    "name": DEFAULT_ASSISTANT_NAME,
    "emoji": DEFAULT_ASSISTANT_EMOJI,
}


def resolve_assistant_identity(
    cfg: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Resolve assistant identity values (name, emoji)."""
    if not cfg:
        return dict(ASSISTANT_IDENTITY_DEFAULTS)
    identity = cfg.get("assistant", {})
    return {
        "name": identity.get("name", DEFAULT_ASSISTANT_NAME),
        "emoji": identity.get("emoji", DEFAULT_ASSISTANT_EMOJI),
    }


# ─── config-ui-hints-types.ts ───

@dataclass
class ConfigUiHint:
    key: str = ""
    label: str = ""
    hint: str = ""
    type: str = "string"  # "string" | "boolean" | "number" | "select"
    options: list[str] = field(default_factory=list)
    required: bool = False


# ─── process-scoped-map.ts ───

class ProcessScopedMap:
    """A process-scoped in-memory key-value map."""

    def __init__(self) -> None:
        self._map: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._map.get(key)

    def set(self, key: str, value: Any) -> None:
        self._map[key] = value

    def delete(self, key: str) -> bool:
        return self._map.pop(key, None) is not None

    def has(self, key: str) -> bool:
        return key in self._map

    def clear(self) -> None:
        self._map.clear()

    def keys(self) -> list[str]:
        return list(self._map.keys())


# ─── tailscale-status.ts ───

TAILSCALE_STATUS_COMMAND_CANDIDATES = [
    "tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
]


def parse_possibly_noisy_json_object(raw: str) -> dict[str, Any]:
    """Parse JSON from a string that may contain non-JSON noise."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        return json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return {}

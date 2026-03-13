"""Gateway boot and misc — ported from bk/src/gateway/ remaining files.

Boot/startup, canvas capability, node command policy, live probes, and more.
Consolidates: boot.ts, call.ts, canvas-capability.ts, node-command-policy.ts,
  node-invoke-sanitize.ts, live-image-probe.ts, live-tool-probe-utils.ts,
  gateway-config-prompts.shared.ts, and remaining small files.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── boot.ts ───

@dataclass
class GatewayBootConfig:
    host: str = "0.0.0.0"
    port: int = 18789
    mode: str = "local"
    force: bool = False
    config_path: str = ""


@dataclass
class GatewayBootResult:
    success: bool = False
    url: str = ""
    pid: int = 0
    error: str | None = None
    started_at_ms: int = 0


# ─── call.ts ───

@dataclass
class GatewayCallOptions:
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30_000
    url: str = ""
    token: str = ""


@dataclass
class GatewayCallResult:
    success: bool = False
    data: Any = None
    error: str | None = None
    status_code: int = 0


# ─── canvas-capability.ts ───

@dataclass
class CanvasCapability:
    supported: bool = False
    max_width: int = 0
    max_height: int = 0
    formats: list[str] = field(default_factory=list)


def resolve_canvas_capability(cfg: dict[str, Any] | None = None) -> CanvasCapability:
    if not cfg:
        return CanvasCapability()
    canvas = cfg.get("canvas", {})
    if not isinstance(canvas, dict):
        return CanvasCapability()
    return CanvasCapability(
        supported=bool(canvas.get("enabled", False)),
        max_width=int(canvas.get("maxWidth", 0)),
        max_height=int(canvas.get("maxHeight", 0)),
        formats=canvas.get("formats", []),
    )


# ─── node-command-policy.ts ───

ALLOWED_NODE_COMMANDS = frozenset({
    "status", "exec", "shell", "restart",
    "update", "config", "logs", "health",
})


def is_node_command_allowed(command: str) -> bool:
    """Check if a node command is allowed."""
    return command.strip().lower() in ALLOWED_NODE_COMMANDS


# ─── node-invoke-sanitize.ts ───

_DANGEROUS_CHARS_RE = re.compile(r"[;&|`$(){}]")


def sanitize_node_invoke_args(args: list[str]) -> list[str]:
    """Sanitize node invoke arguments."""
    return [_DANGEROUS_CHARS_RE.sub("", a) for a in args]


# ─── live-image-probe.ts / live-tool-probe-utils.ts ───

@dataclass
class ProbeResult:
    success: bool = False
    latency_ms: int = 0
    error: str | None = None
    data: Any = None


async def probe_endpoint(url: str, timeout_ms: int = 5000) -> ProbeResult:
    """Probe an HTTP endpoint for connectivity."""
    import httpx
    start = int(time.time() * 1000)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=timeout_ms / 1000.0)
            latency = int(time.time() * 1000) - start
            return ProbeResult(
                success=resp.status_code < 400,
                latency_ms=latency,
            )
    except Exception as e:
        latency = int(time.time() * 1000) - start
        return ProbeResult(success=False, latency_ms=latency, error=str(e))


# ─── gateway-config-prompts.shared.ts ───

GATEWAY_CONFIG_PROMPTS = {
    "port": "Gateway port (default: 18789)",
    "mode": "Bind mode: local, loopback, or tailscale",
    "authMode": "Auth mode: none, token, or device",
    "authToken": "Auth token (leave empty for auto-generated)",
}

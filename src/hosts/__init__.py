"""Canvas/Node host and WhatsApp bridge stubs.

Ported from bk/src/canvas-host/ (~3 TS files),
bk/src/node-host/ (~10 TS files), bk/src/whatsapp/ (~2 TS files),
bk/src/compat/ (~1 TS file).

Minimal stubs — these are specialized runtime hosts
that depend on platform-specific features.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─── Canvas host (bk/src/canvas-host/) ───

@dataclass
class CanvasHostConfig:
    """Configuration for the A2UI canvas host."""
    enabled: bool = False
    bundle_hash: str = ""
    port: int = 0


# ─── Node host (bk/src/node-host/) ───

@dataclass
class NodeHostConfig:
    """Configuration for IoT/device node host."""
    enabled: bool = False
    camera_enabled: bool = False
    screen_enabled: bool = False
    media_dir: str = ""


@dataclass
class NodeInfo:
    id: str = ""
    name: str = ""
    node_type: str = ""  # "camera" | "screen" | "sensor"
    status: str = "offline"
    capabilities: list[str] = field(default_factory=list)


# ─── WhatsApp bridge stub ───

@dataclass
class WhatsAppBridgeConfig:
    """WhatsApp bridge-specific configuration (legacy)."""
    enabled: bool = False
    bridge_url: str = ""
    session_id: str = "default"


# ─── Compat layer ───

def ensure_compat() -> None:
    """Ensure compatibility shims are loaded."""
    pass

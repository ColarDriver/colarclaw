"""Pi embedded runner sandbox info — ported from bk/src/agents/pi-embedded-runner/sandbox-info.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EmbeddedSandboxInfo:
    enabled: bool = False
    image: str | None = None
    mount_workspace: bool = True
    network: bool = True
    container_id: str | None = None
    workspace_dir: str | None = None


def build_embedded_sandbox_info(
    sandbox_config: Any = None,
) -> EmbeddedSandboxInfo:
    if not sandbox_config:
        return EmbeddedSandboxInfo()
    return EmbeddedSandboxInfo(
        enabled=getattr(sandbox_config, "enabled", False),
        image=getattr(sandbox_config, "image", None),
        mount_workspace=getattr(sandbox_config, "mount_workspace", True),
        network=getattr(sandbox_config, "network", True),
    )

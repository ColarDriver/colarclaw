"""Sandbox docker — ported from bk/src/agents/sandbox/docker.ts."""
from __future__ import annotations

from typing import Any

from .constants import DEFAULT_SANDBOX_IMAGE, SANDBOX_AGENT_LABEL, SANDBOX_CONTAINER_WORKDIR, SANDBOX_SESSION_LABEL
from .types import SandboxConfig


def build_sandbox_create_args(
    config: SandboxConfig,
    session_id: str | None = None,
    agent_id: str | None = None,
    workspace_dir: str | None = None,
) -> list[str]:
    """Build Docker create arguments for a sandbox container."""
    image = config.image or DEFAULT_SANDBOX_IMAGE
    args = ["docker", "run", "-d", "--rm"]

    if not config.network:
        args.extend(["--network", "none"])

    if workspace_dir and config.mount_workspace:
        args.extend(["-v", f"{workspace_dir}:{SANDBOX_CONTAINER_WORKDIR}"])
        args.extend(["-w", SANDBOX_CONTAINER_WORKDIR])

    if session_id:
        args.extend(["--label", f"{SANDBOX_SESSION_LABEL}={session_id}"])
    if agent_id:
        args.extend(["--label", f"{SANDBOX_AGENT_LABEL}={agent_id}"])

    for key, value in config.labels.items():
        args.extend(["--label", f"{key}={value}"])
    for key, value in config.env.items():
        args.extend(["-e", f"{key}={value}"])
    for mount in config.extra_mounts:
        src = mount.get("source", "")
        dst = mount.get("target", "")
        if src and dst:
            args.extend(["-v", f"{src}:{dst}"])

    args.append(image)
    return args

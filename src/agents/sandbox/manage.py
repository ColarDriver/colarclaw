"""Sandbox manage — ported from bk/src/agents/sandbox/manage.ts."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .constants import SANDBOX_LABEL_PREFIX
from .types import SandboxBrowserInfo, SandboxContainerInfo

log = logging.getLogger("openclaw.agents.sandbox.manage")


async def list_sandbox_containers() -> list[SandboxContainerInfo]:
    """List all sandbox containers."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "-a", "--filter", f"label={SANDBOX_LABEL_PREFIX}",
            "--format", "{{json .}}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        containers = []
        for line in stdout.decode().strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                containers.append(SandboxContainerInfo(
                    container_id=data.get("ID", ""),
                    name=data.get("Names", ""),
                    image=data.get("Image", ""),
                    status=data.get("Status", ""),
                    created=data.get("CreatedAt", ""),
                ))
            except json.JSONDecodeError:
                continue
        return containers
    except Exception as exc:
        log.debug("Failed to list sandbox containers: %s", exc)
        return []


async def remove_sandbox_container(container_id: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", container_id,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def list_sandbox_browsers() -> list[SandboxBrowserInfo]:
    return []


async def remove_sandbox_browser_container(container_id: str) -> bool:
    return await remove_sandbox_container(container_id)

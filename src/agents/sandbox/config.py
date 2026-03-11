"""Sandbox config — ported from bk/src/agents/sandbox/config.ts."""
from __future__ import annotations

from typing import Any

from .types import (SandboxBrowserConfig, SandboxConfig, SandboxDockerConfig,
                    SandboxPruneConfig, SandboxScope)


def resolve_sandbox_scope(config: Any = None) -> SandboxScope:
    if not config:
        return "none"
    sandbox = getattr(config, "sandbox", None)
    if not sandbox:
        return "none"
    scope = getattr(sandbox, "scope", None)
    if scope in ("session", "agent", "workspace"):
        return scope
    return "none"


def resolve_sandbox_config_for_agent(config: Any = None) -> SandboxConfig:
    if not config:
        return SandboxConfig()
    sandbox = getattr(config, "sandbox", None)
    if not sandbox:
        return SandboxConfig()
    return SandboxConfig(
        enabled=getattr(sandbox, "enabled", False),
        image=getattr(sandbox, "image", None),
        network=getattr(sandbox, "network", True),
        mount_workspace=getattr(sandbox, "mount_workspace", True),
        workspace_access=getattr(sandbox, "workspace_access", "read-write"),
    )


def resolve_sandbox_docker_config(config: Any = None) -> SandboxDockerConfig:
    if not config:
        return SandboxDockerConfig()
    sandbox = getattr(config, "sandbox", None)
    docker = getattr(sandbox, "docker", None) if sandbox else None
    if not docker:
        return SandboxDockerConfig()
    return SandboxDockerConfig(
        socket=getattr(docker, "socket", "/var/run/docker.sock"),
        runtime=getattr(docker, "runtime", None),
    )


def resolve_sandbox_browser_config(config: Any = None) -> SandboxBrowserConfig:
    if not config:
        return SandboxBrowserConfig()
    sandbox = getattr(config, "sandbox", None)
    browser = getattr(sandbox, "browser", None) if sandbox else None
    if not browser:
        return SandboxBrowserConfig()
    return SandboxBrowserConfig(
        enabled=getattr(browser, "enabled", False),
        image=getattr(browser, "image", None),
        port=getattr(browser, "port", 9222),
    )


def resolve_sandbox_prune_config(config: Any = None) -> SandboxPruneConfig:
    if not config:
        return SandboxPruneConfig()
    sandbox = getattr(config, "sandbox", None)
    prune = getattr(sandbox, "prune", None) if sandbox else None
    if not prune:
        return SandboxPruneConfig()
    return SandboxPruneConfig(
        enabled=getattr(prune, "enabled", True),
        max_age_hours=getattr(prune, "max_age_hours", 24),
        max_containers=getattr(prune, "max_containers", 50),
    )

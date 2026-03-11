"""Sandbox types — ported from bk/src/agents/sandbox/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SandboxScope = Literal["session", "agent", "workspace", "none"]
SandboxWorkspaceAccess = Literal["read-write", "read-only", "none"]
SandboxToolPolicySource = Literal["config", "default", "agent"]


@dataclass
class SandboxConfig:
    enabled: bool = False
    image: str | None = None
    network: bool = True
    mount_workspace: bool = True
    workspace_access: SandboxWorkspaceAccess = "read-write"
    extra_mounts: list[dict[str, str]] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class SandboxDockerConfig:
    socket: str = "/var/run/docker.sock"
    runtime: str | None = None


@dataclass
class SandboxBrowserConfig:
    enabled: bool = False
    image: str | None = None
    port: int = 9222


@dataclass
class SandboxPruneConfig:
    enabled: bool = True
    max_age_hours: int = 24
    max_containers: int = 50


@dataclass
class SandboxToolPolicy:
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    source: SandboxToolPolicySource = "default"


@dataclass
class SandboxToolPolicyResolved:
    policy: SandboxToolPolicy
    effective_tools: list[str] = field(default_factory=list)
    blocked_reason: str | None = None


@dataclass
class SandboxWorkspaceInfo:
    host_path: str = ""
    container_path: str = "/workspace"
    access: SandboxWorkspaceAccess = "read-write"


@dataclass
class SandboxContext:
    enabled: bool = False
    container_id: str | None = None
    workspace: SandboxWorkspaceInfo | None = None
    scope: SandboxScope = "none"


@dataclass
class SandboxBrowserContext:
    enabled: bool = False
    container_id: str | None = None
    debug_url: str | None = None
    port: int = 9222


@dataclass
class SandboxContainerInfo:
    container_id: str = ""
    name: str = ""
    image: str = ""
    status: str = ""
    created: str = ""
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class SandboxBrowserInfo:
    container_id: str = ""
    name: str = ""
    port: int = 9222
    status: str = ""

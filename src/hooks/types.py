"""Hook type definitions — ported from bk/src/hooks/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HookInstallSpec:
    kind: str  # "bundled" | "npm" | "git"
    id: str | None = None
    label: str | None = None
    package: str | None = None
    repository: str | None = None
    bins: list[str] | None = None


@dataclass
class OpenClawHookMetadata:
    events: list[str]
    always: bool = False
    hook_key: str | None = None
    emoji: str | None = None
    homepage: str | None = None
    export_name: str | None = None  # default: "default"
    os_list: list[str] | None = None
    requires: dict[str, Any] | None = None
    install: list[HookInstallSpec] | None = None


@dataclass
class HookInvocationPolicy:
    enabled: bool = True


@dataclass
class Hook:
    name: str
    description: str
    source: str  # "openclaw-bundled" | "openclaw-managed" | "openclaw-workspace" | "openclaw-plugin"
    file_path: str  # Path to HOOK.md
    base_dir: str  # Directory containing hook
    handler_path: str  # Path to handler module
    plugin_id: str | None = None


@dataclass
class HookEntry:
    hook: Hook
    frontmatter: dict[str, str]
    metadata: OpenClawHookMetadata | None = None
    invocation: HookInvocationPolicy | None = None


@dataclass
class HookSnapshot:
    hooks: list[dict[str, Any]]
    resolved_hooks: list[Hook] | None = None
    version: int | None = None

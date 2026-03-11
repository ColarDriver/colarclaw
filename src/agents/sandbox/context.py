"""Sandbox context — ported from bk/src/agents/sandbox/context.ts."""
from __future__ import annotations

import os
from typing import Any

from .types import SandboxContext, SandboxWorkspaceInfo


def resolve_sandbox_context(
    config: Any = None,
    session_id: str | None = None,
    workspace_dir: str | None = None,
) -> SandboxContext:
    from .config import resolve_sandbox_config_for_agent, resolve_sandbox_scope
    sandbox_config = resolve_sandbox_config_for_agent(config)
    scope = resolve_sandbox_scope(config)

    if not sandbox_config.enabled:
        return SandboxContext(enabled=False, scope="none")

    workspace = None
    if workspace_dir and sandbox_config.mount_workspace:
        workspace = SandboxWorkspaceInfo(
            host_path=os.path.abspath(workspace_dir),
            container_path="/workspace",
            access=sandbox_config.workspace_access,
        )

    return SandboxContext(
        enabled=True,
        workspace=workspace,
        scope=scope,
    )


def ensure_sandbox_workspace_for_session(
    workspace_dir: str,
    session_id: str,
) -> str:
    session_dir = os.path.join(workspace_dir, ".sandbox", session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir

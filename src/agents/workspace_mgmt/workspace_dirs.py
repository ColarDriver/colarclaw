"""Workspace directories — ported from bk/src/agents/workspace-dir.ts + workspace-dirs.ts."""
from __future__ import annotations
import os

def resolve_workspace_dir(workspace: str | None = None) -> str:
    if workspace and workspace.strip():
        return os.path.expanduser(workspace.strip())
    return os.getcwd()

def resolve_workspace_dirs(workspace_dir: str) -> dict[str, str]:
    return {
        "root": workspace_dir,
        "agents": os.path.join(workspace_dir, ".agents"),
        "skills": os.path.join(workspace_dir, ".agents", "skills"),
        "workflows": os.path.join(workspace_dir, ".agents", "workflows"),
    }

def ensure_workspace_dirs(workspace_dir: str) -> None:
    dirs = resolve_workspace_dirs(workspace_dir)
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

"""Workspace directory — ported from bk/src/agents/workspace-dir.ts.

Workspace directory resolution and validation.
"""
from __future__ import annotations

import os


def resolve_workspace_dir(explicit_dir: str | None = None) -> str:
    """Resolve the workspace directory.

    Priority:
    1. Explicit directory passed as argument
    2. OPENCLAW_WORKSPACE_DIR environment variable
    3. Current working directory
    """
    if explicit_dir:
        return os.path.abspath(os.path.expanduser(explicit_dir))

    env_dir = os.environ.get("OPENCLAW_WORKSPACE_DIR", "").strip()
    if env_dir:
        return os.path.abspath(os.path.expanduser(env_dir))

    return os.getcwd()


def is_valid_workspace_dir(dir_path: str) -> bool:
    """Check if a directory is a valid workspace directory."""
    if not dir_path:
        return False
    expanded = os.path.abspath(os.path.expanduser(dir_path))
    return os.path.isdir(expanded)


def normalize_workspace_dir(dir_path: str) -> str:
    """Normalize a workspace directory path."""
    return os.path.abspath(os.path.expanduser(dir_path))


def find_workspace_root(start_dir: str | None = None) -> str | None:
    """Walk up from start_dir looking for workspace markers (.git, package.json, etc.)."""
    current = os.path.abspath(start_dir or os.getcwd())
    markers = [".git", "package.json", "pyproject.toml", ".openclaw", "Cargo.toml", "go.mod"]

    while True:
        for marker in markers:
            if os.path.exists(os.path.join(current, marker)):
                return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None

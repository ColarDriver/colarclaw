"""Bootstrap cache — ported from bk/src/agents/bootstrap-cache.ts.

Caches loaded workspace bootstrap files per session key to avoid
redundant file-system reads during the same session.
"""
from __future__ import annotations

from typing import Any

_cache: dict[str, list[Any]] = {}


async def get_or_load_bootstrap_files(
    workspace_dir: str,
    session_key: str,
) -> list[Any]:
    """Return cached bootstrap files or load them from the workspace."""
    from .workspace import load_workspace_bootstrap_files

    existing = _cache.get(session_key)
    if existing is not None:
        return existing

    files = await load_workspace_bootstrap_files(workspace_dir)
    _cache[session_key] = files
    return files


def clear_bootstrap_snapshot(session_key: str) -> None:
    """Clear cached bootstrap files for a specific session key."""
    _cache.pop(session_key, None)


def clear_bootstrap_snapshot_on_session_rollover(
    session_key: str | None = None,
    previous_session_id: str | None = None,
) -> None:
    """Clear the snapshot when a session rolls over."""
    if not session_key or not previous_session_id:
        return
    clear_bootstrap_snapshot(session_key)


def clear_all_bootstrap_snapshots() -> None:
    """Clear all cached bootstrap snapshots."""
    _cache.clear()

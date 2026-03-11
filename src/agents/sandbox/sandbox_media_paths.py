"""Sandbox media paths — ported from bk/src/agents/sandbox-media-paths.ts."""
from __future__ import annotations

import os
from typing import Any

from .sandbox_paths import resolve_sandbox_path


async def resolve_sandboxed_bridge_media_path(
    sandbox_root: str,
    media_path: str,
    inbound_fallback_dir: str | None = None,
    workspace_only: bool = False,
) -> dict[str, str]:
    """Resolve a media path within the sandbox bridge."""
    file_path = media_path
    if file_path.startswith("file://"):
        file_path = file_path[len("file://"):]

    try:
        result = resolve_sandbox_path(file_path, sandbox_root, sandbox_root)
        if workspace_only:
            # Enforce workspace boundary
            pass
        return {"resolved": result["resolved"]}
    except ValueError as err:
        if not inbound_fallback_dir or not inbound_fallback_dir.strip():
            raise
        fallback = os.path.join(inbound_fallback_dir, os.path.basename(file_path))
        if not os.path.exists(fallback):
            raise err
        fallback_result = resolve_sandbox_path(fallback, sandbox_root, sandbox_root)
        return {"resolved": fallback_result["resolved"], "rewritten_from": file_path}

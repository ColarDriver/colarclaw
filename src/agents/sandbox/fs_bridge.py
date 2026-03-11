"""Sandbox FS bridge — ported from bk/src/agents/sandbox/fs-bridge.ts."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class FsBridgeResolvedPath:
    host_path: str = ""
    container_path: str = ""


class SandboxFsBridge:
    """Bridge between host and sandbox filesystem."""

    def __init__(self, sandbox_root: str, container_workdir: str = "/workspace"):
        self._sandbox_root = os.path.abspath(sandbox_root)
        self._container_workdir = container_workdir

    def resolve_path(self, file_path: str, cwd: str = "") -> FsBridgeResolvedPath:
        resolved = file_path
        if not os.path.isabs(resolved):
            resolved = os.path.join(cwd or self._sandbox_root, resolved)
        resolved = os.path.abspath(resolved)
        rel = os.path.relpath(resolved, self._sandbox_root)
        container_path = os.path.join(self._container_workdir, rel).replace("\\", "/")
        return FsBridgeResolvedPath(host_path=resolved, container_path=container_path)

    async def read_file(self, file_path: str, cwd: str = "") -> bytes:
        resolved = self.resolve_path(file_path, cwd)
        with open(resolved.host_path, "rb") as f:
            return f.read()

    async def stat(self, file_path: str, cwd: str = "") -> dict[str, Any] | None:
        resolved = self.resolve_path(file_path, cwd)
        try:
            st = os.stat(resolved.host_path)
            return {"size": st.st_size, "mtime": st.st_mtime}
        except OSError:
            return None

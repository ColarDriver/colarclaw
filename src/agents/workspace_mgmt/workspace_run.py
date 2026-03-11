"""Workspace run — ported from bk/src/agents/workspace-run.ts."""
from __future__ import annotations
import asyncio
import os
from typing import Any

async def run_in_workspace(command: str, workspace_dir: str, timeout: float = 30.0) -> dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_shell(
            command, cwd=workspace_dir,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "exitCode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }
    except asyncio.TimeoutError:
        return {"exitCode": -1, "stdout": "", "stderr": "Timed out", "timedOut": True}
    except Exception as e:
        return {"exitCode": -1, "stdout": "", "stderr": str(e)}

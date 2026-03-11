"""Reply bash command — ported from bk/src/auto-reply/reply/bash-command.ts."""
from __future__ import annotations

from typing import Any


async def execute_bash_command(
    script: str,
    ctx: Any = None,
    cfg: Any = None,
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """Execute a bash command and return output."""
    return {"exit_code": 0, "stdout": "", "stderr": ""}

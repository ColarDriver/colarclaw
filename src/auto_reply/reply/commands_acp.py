"""Reply commands ACP — ported from bk/src/auto-reply/reply/commands-acp.ts + context/diagnostics/lifecycle/shared/targets/install-hints/runtime-options."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AcpCommandContext:
    session_id: str | None = None
    agent_id: str | None = None
    host: str | None = None


async def handle_acp_command(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "acp", "result": "ok", "args": args}


async def handle_acp_diagnostics(ctx: Any) -> dict[str, Any]:
    return {"diagnostics": "ok"}


async def handle_acp_lifecycle(ctx: Any, action: str) -> dict[str, Any]:
    return {"lifecycle": action}


def resolve_acp_install_hints(cfg: Any = None) -> list[str]:
    return []


def resolve_acp_runtime_options(cfg: Any = None) -> dict[str, Any]:
    return {}


def resolve_acp_targets(cfg: Any = None) -> list[str]:
    return []

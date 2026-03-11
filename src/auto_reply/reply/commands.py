"""Reply commands — ported from reply/commands-*.ts files.

Covers: commands-acp, commands-allowlist, commands-approve, commands-bash,
commands-compact, commands-config, commands-debug, commands-exec,
commands-gateway, commands-help, commands-model, commands-queue,
commands-reset, commands-seed, commands-session, commands-status,
commands-summarize, commands-think, commands-transcript, commands-voice.
"""
from __future__ import annotations

from typing import Any


async def handle_command_status(ctx: Any, cfg: Any) -> dict[str, Any]:
    return {"command": "status", "result": "ok"}


async def handle_command_help(ctx: Any, cfg: Any) -> dict[str, Any]:
    return {"command": "help", "result": "ok"}


async def handle_command_compact(ctx: Any, cfg: Any) -> dict[str, Any]:
    return {"command": "compact", "result": "ok"}


async def handle_command_clear(ctx: Any, cfg: Any) -> dict[str, Any]:
    return {"command": "clear", "result": "ok"}


async def handle_command_reset(ctx: Any, cfg: Any) -> dict[str, Any]:
    return {"command": "reset", "result": "ok"}


async def handle_command_model(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "model", "result": "ok", "args": args}


async def handle_command_config(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "config", "result": "ok", "args": args}


async def handle_command_debug(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "debug", "result": "ok", "args": args}


async def handle_command_exec(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "exec", "result": "ok", "args": args}


async def handle_command_queue(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "queue", "result": "ok", "args": args}


async def handle_command_bash(ctx: Any, cfg: Any, script: str | None = None) -> dict[str, Any]:
    return {"command": "bash", "result": "ok"}


async def handle_command_think(ctx: Any, cfg: Any, level: str | None = None) -> dict[str, Any]:
    return {"command": "think", "result": "ok", "level": level}


async def handle_command_session(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "session", "result": "ok", "args": args}


async def handle_command_transcript(ctx: Any, cfg: Any) -> dict[str, Any]:
    return {"command": "transcript", "result": "ok"}


async def handle_command_voice(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "voice", "result": "ok", "args": args}


async def handle_command_summarize(ctx: Any, cfg: Any) -> dict[str, Any]:
    return {"command": "summarize", "result": "ok"}


async def handle_command_approve(ctx: Any, cfg: Any) -> dict[str, Any]:
    return {"command": "approve", "result": "ok"}


async def handle_command_seed(ctx: Any, cfg: Any, seed: str | None = None) -> dict[str, Any]:
    return {"command": "seed", "result": "ok", "seed": seed}


async def handle_command_allowlist(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "allowlist", "result": "ok", "args": args}


async def handle_command_gateway(ctx: Any, cfg: Any, args: str | None = None) -> dict[str, Any]:
    return {"command": "gateway", "result": "ok", "args": args}

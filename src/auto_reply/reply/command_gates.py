"""Reply command gates — ported from bk/src/auto-reply/reply/command-gates.ts."""
from __future__ import annotations

from typing import Any


def should_gate_command(
    command_key: str,
    ctx: Any = None,
    cfg: Any = None,
) -> bool:
    """Check if a command should be gated (blocked) based on context/config."""
    if not command_key:
        return False

    # If the sender is not authorized, gate the command
    authorized = getattr(ctx, "is_authorized_sender", True) if ctx else True
    return not authorized


def resolve_command_gate_message(command_key: str) -> str:
    return f"Command /{command_key} requires authorization."

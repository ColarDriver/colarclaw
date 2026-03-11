from __future__ import annotations

from datetime import datetime, timezone


async def tool_clock_now(_: dict[str, object]) -> str:
    return datetime.now(timezone.utc).isoformat()


async def tool_echo_text(args: dict[str, object]) -> str:
    text = args.get("text")
    return str(text) if text is not None else ""

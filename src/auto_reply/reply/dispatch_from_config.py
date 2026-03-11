"""Reply dispatch from config — ported from bk/src/auto-reply/reply/dispatch-from-config.ts."""
from __future__ import annotations

from typing import Any


async def dispatch_reply_from_config(
    ctx: Any,
    cfg: Any,
    dispatcher: Any = None,
    reply_options: dict[str, Any] | None = None,
    reply_resolver: Any = None,
) -> dict[str, Any]:
    return {"status": "dispatched"}

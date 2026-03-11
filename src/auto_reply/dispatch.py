"""Auto-reply dispatch — ported from bk/src/auto-reply/dispatch.ts."""
from __future__ import annotations

from typing import Any, Callable


async def with_reply_dispatcher(
    dispatcher: Any,
    run: Callable[..., Any],
    on_settled: Callable[..., Any] | None = None,
) -> Any:
    try:
        return await run()
    finally:
        if hasattr(dispatcher, "mark_complete"):
            dispatcher.mark_complete()
        try:
            if hasattr(dispatcher, "wait_for_idle"):
                await dispatcher.wait_for_idle()
        finally:
            if on_settled:
                result = on_settled()
                if hasattr(result, "__await__"):
                    await result


async def dispatch_inbound_message(
    ctx: Any,
    cfg: Any,
    dispatcher: Any,
    reply_options: dict[str, Any] | None = None,
    reply_resolver: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Dispatch an inbound message through the reply pipeline."""
    return await with_reply_dispatcher(
        dispatcher=dispatcher,
        run=lambda: _dispatch_reply_from_config(ctx, cfg, dispatcher, reply_options, reply_resolver),
    )


async def _dispatch_reply_from_config(
    ctx: Any,
    cfg: Any,
    dispatcher: Any,
    reply_options: dict[str, Any] | None = None,
    reply_resolver: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Dispatch reply from config (placeholder for full pipeline)."""
    return {"status": "dispatched"}

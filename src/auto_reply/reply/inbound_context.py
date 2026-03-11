"""Reply inbound context — ported from bk/src/auto-reply/reply/inbound-context.ts."""
from __future__ import annotations

from typing import Any


def finalize_inbound_context(ctx: Any) -> Any:
    """Finalize / normalize an inbound message context before dispatch."""
    return ctx

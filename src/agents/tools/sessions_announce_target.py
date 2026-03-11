"""Sessions announce target — ported from bk/src/agents/tools/sessions-announce-target.ts."""
from __future__ import annotations

from typing import Any


def resolve_announce_target(
    session_id: str,
    config: Any = None,
) -> str | None:
    if not config:
        return None
    announce = getattr(config, "announce", None)
    if not announce:
        return None
    target = getattr(announce, "target", None)
    return target if isinstance(target, str) and target.strip() else None

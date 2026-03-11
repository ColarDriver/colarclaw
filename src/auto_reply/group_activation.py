"""Auto-reply group activation — ported from bk/src/auto-reply/group-activation.ts."""
from __future__ import annotations

from typing import Literal

GroupActivationMode = Literal["mention", "always"]


def normalize_group_activation(raw: str | None = None) -> GroupActivationMode | None:
    value = (raw or "").strip().lower()
    if value == "mention":
        return "mention"
    if value == "always":
        return "always"
    return None


def parse_activation_command(raw: str | None = None) -> dict[str, bool | GroupActivationMode | None]:
    if not raw:
        return {"has_command": False}
    trimmed = raw.strip()
    if not trimmed:
        return {"has_command": False}
    import re
    match = re.match(r"^/activation(?:\s+([a-zA-Z]+))?\s*$", trimmed, re.IGNORECASE)
    if not match:
        return {"has_command": False}
    mode = normalize_group_activation(match.group(1))
    return {"has_command": True, "mode": mode}

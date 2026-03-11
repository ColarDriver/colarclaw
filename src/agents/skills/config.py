"""Skill config — ported from bk/src/agents/skills/config.ts."""
from __future__ import annotations

from typing import Any


def resolve_skills_config(config: Any | None = None) -> dict[str, Any]:
    """Resolve skills configuration from agent config."""
    if not config:
        return {"enabled": True, "dirs": []}
    agents = getattr(config, "agents", None)
    if not agents:
        return {"enabled": True, "dirs": []}
    skills_cfg = getattr(agents, "skills", None)
    if not skills_cfg:
        return {"enabled": True, "dirs": []}
    return {
        "enabled": getattr(skills_cfg, "enabled", True),
        "dirs": getattr(skills_cfg, "dirs", []),
    }

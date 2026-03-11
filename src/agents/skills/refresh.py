"""Skill refresh — ported from bk/src/agents/skills/refresh.ts."""
from __future__ import annotations

from typing import Any

from .types import SkillDefinition
from .workspace import discover_workspace_skills


def refresh_skills(workspace_dir: str, existing: list[SkillDefinition] | None = None) -> list[SkillDefinition]:
    """Refresh skills list from workspace, merging with existing."""
    discovered = discover_workspace_skills(workspace_dir)
    if not existing:
        return discovered
    existing_names = {s.name for s in existing}
    merged = list(existing)
    for skill in discovered:
        if skill.name not in existing_names:
            merged.append(skill)
    return merged

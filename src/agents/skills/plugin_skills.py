"""Skill plugin skills — ported from bk/src/agents/skills/plugin-skills.ts."""
from __future__ import annotations

from typing import Any

from .types import SkillDefinition


def merge_plugin_skills(
    workspace_skills: list[SkillDefinition],
    plugin_skills: list[SkillDefinition],
) -> list[SkillDefinition]:
    """Merge plugin skills with workspace skills (workspace takes precedence)."""
    ws_names = {s.name for s in workspace_skills}
    merged = list(workspace_skills)
    for skill in plugin_skills:
        if skill.name not in ws_names:
            merged.append(skill)
    return merged

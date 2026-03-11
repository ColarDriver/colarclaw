"""Skill bundled context — ported from bk/src/agents/skills/bundled-context.ts."""
from __future__ import annotations

from typing import Any

from .types import SkillDefinition


def build_bundled_skill_context(skills: list[SkillDefinition]) -> str:
    """Build bundled skill context for embedding in prompts."""
    if not skills:
        return ""
    entries = []
    for skill in skills:
        if not skill.enabled or not skill.content:
            continue
        entries.append(f"### {skill.name}\n{skill.content}")
    return "\n\n".join(entries)

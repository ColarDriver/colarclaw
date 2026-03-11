"""Skill serialize — ported from bk/src/agents/skills/serialize.ts."""
from __future__ import annotations

from .types import SkillDefinition


def serialize_skill_for_prompt(skill: SkillDefinition) -> str:
    """Serialize a skill for inclusion in the system prompt."""
    parts = ["<skill>"]
    parts.append(f"<name>{skill.name}</name>")
    if skill.description:
        parts.append(f"<description>{skill.description}</description>")
    if skill.content:
        parts.append(f"<content>\n{skill.content}\n</content>")
    parts.append("</skill>")
    return "\n".join(parts)


def serialize_skills_for_prompt(skills: list[SkillDefinition]) -> str:
    """Serialize multiple skills for the system prompt."""
    if not skills:
        return ""
    blocks = [serialize_skill_for_prompt(s) for s in skills if s.enabled]
    return "\n\n".join(blocks)

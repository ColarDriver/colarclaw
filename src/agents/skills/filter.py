"""Skill filter — ported from bk/src/agents/skills/filter.ts."""
from __future__ import annotations

from typing import Any

from .types import SkillDefinition


def filter_skills(
    skills: list[SkillDefinition],
    enabled_only: bool = True,
    source: str | None = None,
    tags: list[str] | None = None,
) -> list[SkillDefinition]:
    """Filter skills by criteria."""
    result = skills
    if enabled_only:
        result = [s for s in result if s.enabled]
    if source:
        result = [s for s in result if s.source == source]
    if tags:
        tag_set = set(tags)
        result = [s for s in result if s.frontmatter and tag_set.intersection(s.frontmatter.tags)]
    return result

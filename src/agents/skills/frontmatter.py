"""Skill frontmatter — ported from bk/src/agents/skills/frontmatter.ts."""
from __future__ import annotations

import re
from typing import Any

from .types import SkillFrontmatter


def parse_skill_frontmatter(content: str) -> tuple[SkillFrontmatter | None, str]:
    """Parse YAML frontmatter from a skill file."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None, content

    frontmatter_text = match.group(1)
    body = content[match.end():]

    fm = SkillFrontmatter()
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip("'\"")
        if key == "name":
            fm.name = value
        elif key == "description":
            fm.description = value
        elif key == "enabled":
            fm.enabled = value.lower() not in ("false", "0", "no")

    return fm, body

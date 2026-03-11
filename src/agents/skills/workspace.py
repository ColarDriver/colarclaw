"""Skill workspace — ported from bk/src/agents/skills/workspace.ts."""
from __future__ import annotations

import os
from typing import Any

from .frontmatter import parse_skill_frontmatter
from .types import SkillDefinition

SKILL_FILENAME = "SKILL.md"
SKILL_DIRS = [".agents/skills", ".agent/skills", "_agents/skills", "_agent/skills"]


def discover_workspace_skills(workspace_dir: str) -> list[SkillDefinition]:
    """Discover skills in the workspace directory."""
    skills: list[SkillDefinition] = []
    for skill_dir in SKILL_DIRS:
        full_dir = os.path.join(workspace_dir, skill_dir)
        if not os.path.isdir(full_dir):
            continue
        for entry in os.listdir(full_dir):
            skill_path = os.path.join(full_dir, entry, SKILL_FILENAME)
            if os.path.isfile(skill_path):
                try:
                    with open(skill_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    fm, body = parse_skill_frontmatter(content)
                    skills.append(SkillDefinition(
                        name=fm.name if fm else entry,
                        description=fm.description if fm else "",
                        path=skill_path, content=body, source="workspace",
                        frontmatter=fm, enabled=fm.enabled if fm else True,
                    ))
                except Exception:
                    pass
    return skills

"""Skill bundled dir — ported from bk/src/agents/skills/bundled-dir.ts."""
from __future__ import annotations

import os
from typing import Any


def resolve_bundled_skills_dir() -> str:
    """Resolve the bundled skills directory."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "bundled-skills")


def list_bundled_skill_names() -> list[str]:
    """List bundled skill directory names."""
    skills_dir = resolve_bundled_skills_dir()
    if not os.path.isdir(skills_dir):
        return []
    return sorted([
        d for d in os.listdir(skills_dir)
        if os.path.isdir(os.path.join(skills_dir, d))
        and os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))
    ])

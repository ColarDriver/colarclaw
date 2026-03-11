"""Skill types — ported from bk/src/agents/skills/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillFrontmatter:
    name: str = ""
    description: str = ""
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class SkillDefinition:
    name: str = ""
    description: str = ""
    path: str = ""
    content: str = ""
    source: str = "workspace"  # workspace | plugin | bundled
    frontmatter: SkillFrontmatter | None = None
    enabled: bool = True

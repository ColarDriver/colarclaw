"""Skills management — ported from bk/src/agents/skills*.ts.

Agent skill installation, status tracking, and filtering.
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("openclaw.agents.skills")

@dataclass
class SkillMetadata:
    id: str
    name: str
    description: str = ""
    version: str = ""
    path: str = ""
    enabled: bool = True
    tags: list[str] = field(default_factory=list)

@dataclass
class SkillStatus:
    id: str
    installed: bool = False
    enabled: bool = True
    version: str = ""
    path: str = ""
    error: str | None = None

def normalize_skill_filter(skills: list[str] | None) -> list[str] | None:
    if skills is None:
        return None
    return [s.strip().lower() for s in skills if isinstance(s, str) and s.strip()]

def load_skill_metadata(skill_dir: str) -> SkillMetadata | None:
    skill_file = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_file):
        return None
    try:
        with open(skill_file, "r", encoding="utf-8") as f:
            content = f.read()
        name = os.path.basename(skill_dir)
        description = ""
        lines = content.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("description:"):
                description = stripped[len("description:"):].strip().strip("'\"")
                break
            if stripped.startswith("name:"):
                name = stripped[len("name:"):].strip().strip("'\"")
        return SkillMetadata(id=name.lower(), name=name, description=description, path=skill_dir)
    except Exception as e:
        log.warning("Failed to load skill metadata from %s: %s", skill_dir, e)
        return None

def discover_skills(workspace_dir: str) -> list[SkillMetadata]:
    skills: list[SkillMetadata] = []
    for dir_name in (".agents", ".agent", "_agents", "_agent"):
        skills_root = os.path.join(workspace_dir, dir_name, "skills")
        if not os.path.isdir(skills_root):
            continue
        for entry in os.listdir(skills_root):
            skill_dir = os.path.join(skills_root, entry)
            if os.path.isdir(skill_dir):
                meta = load_skill_metadata(skill_dir)
                if meta:
                    skills.append(meta)
    return skills

def check_skill_status(skill_id: str, workspace_dir: str) -> SkillStatus:
    for skill in discover_skills(workspace_dir):
        if skill.id == skill_id.lower():
            return SkillStatus(id=skill_id, installed=True, enabled=skill.enabled, path=skill.path)
    return SkillStatus(id=skill_id, installed=False)

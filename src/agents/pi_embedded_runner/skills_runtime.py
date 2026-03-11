"""Pi embedded runner skills runtime — ported from bk/src/agents/pi-embedded-runner/skills-runtime.ts."""
from __future__ import annotations

from typing import Any

from ..skills.types import SkillDefinition
from ..skills.workspace import discover_workspace_skills


def resolve_runtime_skills(
    workspace_dir: str | None = None,
    config: Any = None,
) -> list[SkillDefinition]:
    """Resolve skills available at runtime for an embedded runner."""
    if not workspace_dir:
        return []
    return discover_workspace_skills(workspace_dir)

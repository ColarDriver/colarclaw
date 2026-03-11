"""Workspace templates — ported from bk/src/agents/workspace-templates.ts."""
from __future__ import annotations
import os
from typing import Any

DEFAULT_AGENTS_MD = """# Agent Guidelines

Add your project-specific instructions here.
"""

DEFAULT_SOUL_MD = """# Agent Identity

You are a helpful coding assistant.
"""

TEMPLATE_FILES: dict[str, str] = {
    "AGENTS.md": DEFAULT_AGENTS_MD,
    "SOUL.md": DEFAULT_SOUL_MD,
}

def create_workspace_template(workspace_dir: str, template_name: str | None = None) -> list[str]:
    created: list[str] = []
    agents_dir = os.path.join(workspace_dir, ".agents")
    os.makedirs(agents_dir, exist_ok=True)
    for filename, content in TEMPLATE_FILES.items():
        filepath = os.path.join(agents_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            created.append(filepath)
    return created

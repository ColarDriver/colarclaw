"""Skill tools dir — ported from bk/src/agents/skills/tools-dir.ts."""
from __future__ import annotations

import os
from typing import Any

TOOLS_DIR_NAMES = [".agents/tools", ".agent/tools", "_agents/tools", "_agent/tools"]


def resolve_tools_dir(workspace_dir: str) -> str | None:
    """Resolve the tools directory in the workspace."""
    for name in TOOLS_DIR_NAMES:
        full = os.path.join(workspace_dir, name)
        if os.path.isdir(full):
            return full
    return None

"""Skill env overrides — ported from bk/src/agents/skills/env-overrides.ts."""
from __future__ import annotations

import os
from typing import Any


def resolve_skill_env_overrides() -> dict[str, str]:
    """Resolve environment variable overrides for skills."""
    overrides: dict[str, str] = {}
    prefix = "OPENCLAW_SKILL_"
    for key, value in os.environ.items():
        if key.startswith(prefix) and value:
            overrides[key] = value
    return overrides

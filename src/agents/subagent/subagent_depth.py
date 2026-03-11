"""Subagent depth — ported from bk/src/agents/subagent-depth.ts."""
from __future__ import annotations

MAX_SUBAGENT_DEPTH = 5

def resolve_subagent_depth(parent_depth: int = 0) -> int:
    return parent_depth + 1

def is_max_depth_reached(depth: int, max_depth: int = MAX_SUBAGENT_DEPTH) -> bool:
    return depth >= max_depth

def validate_subagent_depth(depth: int, max_depth: int = MAX_SUBAGENT_DEPTH) -> None:
    if is_max_depth_reached(depth, max_depth):
        raise ValueError(f"Maximum subagent depth ({max_depth}) exceeded at depth {depth}")

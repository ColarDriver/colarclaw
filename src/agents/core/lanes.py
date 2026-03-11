"""Lanes — ported from bk/src/agents/lanes.ts.

Message processing lanes for routing and priority.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal

LanePriority = Literal["high", "normal", "low", "background"]

@dataclass
class Lane:
    id: str
    priority: LanePriority = "normal"
    session_key: str = ""
    agent_id: str = ""
    active: bool = True

def resolve_lane_priority(lane: Lane) -> int:
    mapping = {"high": 3, "normal": 2, "low": 1, "background": 0}
    return mapping.get(lane.priority, 2)

def sort_lanes_by_priority(lanes: list[Lane]) -> list[Lane]:
    return sorted(lanes, key=lambda l: resolve_lane_priority(l), reverse=True)

def find_lane(lanes: list[Lane], session_key: str) -> Lane | None:
    for lane in lanes:
        if lane.session_key == session_key:
            return lane
    return None

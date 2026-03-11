"""Pi embedded runner lanes — ported from bk/src/agents/pi-embedded-runner/lanes.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

LaneKind = Literal["primary", "background", "tool"]


@dataclass
class Lane:
    kind: LaneKind = "primary"
    id: str = ""
    active: bool = True
    pending_tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LaneManager:
    def __init__(self):
        self._lanes: dict[str, Lane] = {}
        self._primary = Lane(kind="primary", id="primary", active=True)
        self._lanes["primary"] = self._primary

    @property
    def primary(self) -> Lane:
        return self._primary

    def create(self, lane_id: str, kind: LaneKind = "background") -> Lane:
        lane = Lane(kind=kind, id=lane_id, active=True)
        self._lanes[lane_id] = lane
        return lane

    def get(self, lane_id: str) -> Lane | None:
        return self._lanes.get(lane_id)

    def deactivate(self, lane_id: str) -> None:
        lane = self._lanes.get(lane_id)
        if lane:
            lane.active = False

    def list_active(self) -> list[Lane]:
        return [l for l in self._lanes.values() if l.active]

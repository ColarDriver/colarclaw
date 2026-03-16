from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WsEvent:
    type: str
    payload: dict[str, object]

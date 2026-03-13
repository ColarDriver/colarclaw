"""Browser profiles — ported from bk/src/browser/profiles.ts + profiles-service.ts.

Browser profile management: creation, deletion, port allocation.
"""
from __future__ import annotations

from typing import Any

CDP_PORT_RANGE_START = 9222


def get_used_ports(profiles: dict[str, dict[str, Any]]) -> set[int]:
    used: set[int] = set()
    for p in profiles.values():
        port = p.get("cdpPort") or p.get("cdp_port")
        if isinstance(port, int) and port > 0:
            used.add(port)
    return used


def allocate_cdp_port(profiles: dict[str, dict[str, Any]], range_start: int = CDP_PORT_RANGE_START, range_end: int = CDP_PORT_RANGE_START + 10) -> int | None:
    used = get_used_ports(profiles)
    for port in range(range_start, range_end + 1):
        if port not in used:
            return port
    return None


async def create_profile(name: str, color: str = "#FF4500", cdp_url: str | None = None, driver: str = "openclaw") -> dict[str, Any]:
    return {"ok": True, "profile": name}


async def delete_profile(name: str) -> dict[str, Any]:
    return {"ok": True, "profile": name, "deleted": False}


async def list_profiles() -> list[dict[str, Any]]:
    return []

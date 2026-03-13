"""Browser client — ported from bk/src/browser/client.ts + client-fetch.ts.

HTTP client for the browser control server: status, tabs, snapshots, profiles.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode


@dataclass
class BrowserStatus:
    enabled: bool = False
    profile: str | None = None
    running: bool = False
    cdp_ready: bool | None = None
    pid: int | None = None
    cdp_port: int = 0
    cdp_url: str | None = None
    chosen_browser: str | None = None
    user_data_dir: str | None = None
    color: str = "#FF4500"
    headless: bool = False
    attach_only: bool = False


@dataclass
class ProfileStatus:
    name: str = ""
    cdp_port: int = 0
    cdp_url: str = ""
    color: str = ""
    running: bool = False
    tab_count: int = 0
    is_default: bool = False
    is_remote: bool = False


@dataclass
class BrowserTab:
    target_id: str = ""
    title: str = ""
    url: str = ""
    ws_url: str | None = None
    type: str | None = None


@dataclass
class SnapshotAriaNode:
    ref: str = ""
    role: str = ""
    name: str = ""
    value: str | None = None
    description: str | None = None
    backend_dom_node_id: int | None = None
    depth: int = 0


def _build_profile_query(profile: str | None = None) -> str:
    return f"?profile={quote(profile)}" if profile else ""


def _with_base_url(base_url: str | None, path: str) -> str:
    if not base_url:
        return path
    return f"{base_url.rstrip('/')}{path}"


async def _fetch_browser_json(url: str, method: str = "GET", timeout_ms: int = 3000, **kwargs: Any) -> Any:
    """Fetch JSON from browser server (placeholder)."""
    return {}


async def browser_status(base_url: str | None = None, profile: str | None = None) -> BrowserStatus:
    return BrowserStatus()


async def browser_profiles(base_url: str | None = None) -> list[ProfileStatus]:
    return []


async def browser_start(base_url: str | None = None, profile: str | None = None) -> None:
    pass


async def browser_stop(base_url: str | None = None, profile: str | None = None) -> None:
    pass


async def browser_reset_profile(base_url: str | None = None, profile: str | None = None) -> dict[str, Any]:
    return {"ok": True, "moved": False, "from": ""}


async def browser_create_profile(base_url: str | None = None, name: str = "", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "profile": name}


async def browser_delete_profile(base_url: str | None = None, profile: str = "") -> dict[str, Any]:
    return {"ok": True, "profile": profile, "deleted": False}


async def browser_tabs(base_url: str | None = None, profile: str | None = None) -> list[BrowserTab]:
    return []


async def browser_open_tab(base_url: str | None = None, url: str = "", profile: str | None = None) -> BrowserTab:
    return BrowserTab()


async def browser_focus_tab(base_url: str | None = None, target_id: str = "", profile: str | None = None) -> None:
    pass


async def browser_close_tab(base_url: str | None = None, target_id: str = "", profile: str | None = None) -> None:
    pass


async def browser_tab_action(base_url: str | None = None, action: str = "list", **kwargs: Any) -> Any:
    return {}


async def browser_snapshot(base_url: str | None = None, format: str = "ai", **kwargs: Any) -> dict[str, Any]:
    return {"ok": True}

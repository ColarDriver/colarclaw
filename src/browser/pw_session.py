"""Browser Playwright session — ported from bk/src/browser/pw-session.ts.

Playwright-based browser session: connection management, page state tracking,
console/error/network monitoring, role refs, screenshots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserConsoleMessage:
    type: str = ""
    text: str = ""
    timestamp: str = ""
    location: dict[str, Any] | None = None


@dataclass
class BrowserPageError:
    message: str = ""
    name: str | None = None
    stack: str | None = None
    timestamp: str = ""


@dataclass
class BrowserNetworkRequest:
    id: str = ""
    timestamp: str = ""
    method: str = ""
    url: str = ""
    resource_type: str | None = None
    status: int | None = None
    ok: bool | None = None
    failure_text: str | None = None


@dataclass
class PageState:
    console: list[BrowserConsoleMessage] = field(default_factory=list)
    errors: list[BrowserPageError] = field(default_factory=list)
    requests: list[BrowserNetworkRequest] = field(default_factory=list)
    next_request_id: int = 0
    role_refs: dict[str, dict[str, Any]] | None = None
    role_refs_mode: str | None = None
    role_refs_frame_selector: str | None = None


MAX_CONSOLE_MESSAGES = 500
MAX_PAGE_ERRORS = 200
MAX_NETWORK_REQUESTS = 500
MAX_ROLE_REFS_CACHE = 50

_page_states: dict[int, PageState] = {}
_role_refs_by_target: dict[str, dict[str, Any]] = {}


def ensure_page_state(page_id: int) -> PageState:
    if page_id not in _page_states:
        _page_states[page_id] = PageState()
    return _page_states[page_id]


def store_role_refs_for_target(cdp_url: str, target_id: str, refs: dict[str, Any], mode: str = "role", frame_selector: str | None = None) -> None:
    key = f"{cdp_url.rstrip('/')}::{target_id}"
    _role_refs_by_target[key] = {"refs": refs, "mode": mode, "frame_selector": frame_selector}
    while len(_role_refs_by_target) > MAX_ROLE_REFS_CACHE:
        first = next(iter(_role_refs_by_target))
        del _role_refs_by_target[first]


def restore_role_refs_for_target(cdp_url: str, target_id: str) -> dict[str, Any] | None:
    key = f"{cdp_url.rstrip('/')}::{target_id}"
    return _role_refs_by_target.get(key)


async def connect_browser(cdp_url: str) -> Any:
    """Connect to browser via Playwright (placeholder)."""
    return None


async def get_page_for_target_id(cdp_url: str, target_id: str | None = None) -> Any:
    """Get Playwright Page for a CDP target (placeholder)."""
    return None


async def close_playwright_browser_connection() -> None:
    """Close the Playwright browser connection (placeholder)."""
    pass


async def force_disconnect_playwright_for_target(cdp_url: str, target_id: str | None = None, reason: str | None = None) -> None:
    """Force disconnect for stuck operations (placeholder)."""
    pass


async def list_pages_via_playwright(cdp_url: str) -> list[dict[str, str]]:
    """List pages via Playwright (placeholder)."""
    return []


async def create_page_via_playwright(cdp_url: str, url: str = "about:blank", ssrf_policy: Any = None) -> dict[str, str]:
    """Create new page via Playwright (placeholder)."""
    return {"targetId": "", "title": "", "url": url, "type": "page"}


async def close_page_by_target_id_via_playwright(cdp_url: str, target_id: str = "") -> None:
    """Close page by targetId (placeholder)."""
    pass

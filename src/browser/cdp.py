"""Browser CDP — ported from bk/src/browser/cdp.ts + cdp.helpers.ts + cdp-timeouts.ts + cdp-proxy-bypass.ts.

Chrome DevTools Protocol: WebSocket connections, screenshots, JS evaluation,
accessibility snapshots, DOM snapshots, query selectors.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse


def normalize_cdp_ws_url(ws_url: str, cdp_url: str) -> str:
    """Normalize a CDP WebSocket URL against the main CDP HTTP URL."""
    try:
        ws = urlparse(ws_url)
        cdp = urlparse(cdp_url)
        hostname = ws.hostname or ""
        is_loopback = hostname.lower() in ("localhost", "127.0.0.1", "::1")
        cdp_is_loopback = (cdp.hostname or "").lower() in ("localhost", "127.0.0.1", "::1")
        if is_loopback and not cdp_is_loopback:
            scheme = "wss" if cdp.scheme == "https" else "ws"
            port = cdp.port or (443 if cdp.scheme == "https" else 80)
            return urlunparse((scheme, f"{cdp.hostname}:{port}", ws.path, ws.params, ws.query, ws.fragment))
        return ws_url
    except Exception:
        return ws_url


@dataclass
class CdpRemoteObject:
    type: str = ""
    subtype: str | None = None
    value: Any = None
    description: str | None = None


@dataclass
class CdpExceptionDetails:
    text: str | None = None
    line_number: int | None = None
    column_number: int | None = None
    exception: CdpRemoteObject | None = None


@dataclass
class AriaSnapshotNode:
    ref: str = ""
    role: str = "unknown"
    name: str = ""
    value: str | None = None
    description: str | None = None
    backend_dom_node_id: int | None = None
    depth: int = 0


@dataclass
class DomSnapshotNode:
    ref: str = ""
    parent_ref: str | None = None
    depth: int = 0
    tag: str = ""
    id: str | None = None
    class_name: str | None = None
    role: str | None = None
    name: str | None = None
    text: str | None = None
    href: str | None = None
    type: str | None = None
    value: str | None = None


@dataclass
class QueryMatch:
    index: int = 0
    tag: str = ""
    id: str | None = None
    class_name: str | None = None
    text: str | None = None
    value: str | None = None
    href: str | None = None
    outer_html: str | None = None


def _ax_value(v: Any) -> str:
    if not v or not isinstance(v, dict):
        return ""
    val = v.get("value")
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    return ""


def format_aria_snapshot(nodes: list[dict[str, Any]], limit: int) -> list[AriaSnapshotNode]:
    by_id: dict[str, dict[str, Any]] = {}
    for n in nodes:
        nid = n.get("nodeId")
        if nid:
            by_id[nid] = n
    referenced: set[str] = set()
    for n in nodes:
        for c in n.get("childIds", []):
            referenced.add(c)
    root = next((n for n in nodes if n.get("nodeId") and n["nodeId"] not in referenced), nodes[0] if nodes else None)
    if not root or not root.get("nodeId"):
        return []
    out: list[AriaSnapshotNode] = []
    stack = [{"id": root["nodeId"], "depth": 0}]
    while stack and len(out) < limit:
        item = stack.pop()
        n = by_id.get(item["id"])
        if not n:
            continue
        out.append(AriaSnapshotNode(
            ref=f"ax{len(out) + 1}", role=_ax_value(n.get("role")) or "unknown",
            name=_ax_value(n.get("name")), value=_ax_value(n.get("value")) or None,
            description=_ax_value(n.get("description")) or None,
            backend_dom_node_id=n.get("backendDOMNodeId"), depth=item["depth"],
        ))
        children = [c for c in n.get("childIds", []) if c in by_id]
        for c in reversed(children):
            stack.append({"id": c, "depth": item["depth"] + 1})
    return out


async def capture_screenshot_png(ws_url: str, full_page: bool = False) -> bytes:
    """Capture PNG screenshot via CDP (placeholder)."""
    return b""


async def capture_screenshot(ws_url: str, full_page: bool = False, fmt: str = "png", quality: int = 85) -> bytes:
    """Capture screenshot via CDP (placeholder)."""
    return b""


async def create_target_via_cdp(cdp_url: str, url: str, ssrf_policy: Any = None) -> dict[str, str]:
    """Create new tab via CDP Target.createTarget (placeholder)."""
    return {"targetId": ""}


async def evaluate_javascript(ws_url: str, expression: str, await_promise: bool = False, return_by_value: bool = True) -> dict[str, Any]:
    """Evaluate JS via CDP Runtime.evaluate (placeholder)."""
    return {"result": {"type": "undefined"}}


async def snapshot_aria(ws_url: str, limit: int = 500) -> dict[str, list[AriaSnapshotNode]]:
    """Get accessibility snapshot via CDP (placeholder)."""
    return {"nodes": []}


async def snapshot_dom(ws_url: str, limit: int = 800, max_text_chars: int = 220) -> dict[str, list[DomSnapshotNode]]:
    """Get DOM snapshot via CDP evaluate (placeholder)."""
    return {"nodes": []}


async def get_dom_text(ws_url: str, fmt: str = "text", max_chars: int = 200_000, selector: str | None = None) -> dict[str, str]:
    """Get DOM text content (placeholder)."""
    return {"text": ""}


async def query_selector(ws_url: str, selector: str, limit: int = 20, max_text_chars: int = 500, max_html_chars: int = 1500) -> dict[str, list[QueryMatch]]:
    """Run CSS query selector (placeholder)."""
    return {"matches": []}


def append_cdp_path(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


async def fetch_json(url: str, timeout_ms: int = 1500) -> Any:
    """Fetch JSON from HTTP endpoint (placeholder)."""
    return {}


def get_headers_with_auth(url: str) -> dict[str, str]:
    """Get request headers with auth if needed."""
    return {}


# CDP timeout helpers
DEFAULT_CDP_SOCKET_TIMEOUT_MS = 5000
DEFAULT_CDP_HANDSHAKE_TIMEOUT_MS = 3000


# CDP proxy bypass
def with_no_proxy_for_cdp_url(cdp_url: str) -> dict[str, str]:
    """Return env vars to bypass proxy for CDP URL."""
    try:
        host = urlparse(cdp_url).hostname or ""
        if host.lower() in ("localhost", "127.0.0.1", "::1"):
            return {"NO_PROXY": host}
    except Exception:
        pass
    return {}

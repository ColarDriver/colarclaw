"""Shared node utilities — ported from bk/src/shared/node-match.ts,
node-list-types.ts, node-list-parse.ts, node-resolve.ts.

Node matching, listing, and resolution for Tailscale/mesh network nodes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ─── node-list-types.ts ───

@dataclass
class NodeListEntry:
    node_id: str = ""
    display_name: str = ""
    remote_ip: str = ""
    connected: bool = False
    os: str = ""
    hostname: str = ""
    tags: list[str] = field(default_factory=list)


# ─── node-match.ts ───

def normalize_node_key(value: str) -> str:
    """Normalize a node key for matching."""
    cleaned = value.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    return cleaned.strip("-")


def resolve_node_matches(
    nodes: list[NodeListEntry | dict[str, Any]],
    query: str,
) -> list[NodeListEntry | dict[str, Any]]:
    """Find nodes matching a query string."""
    q = query.strip()
    if not q:
        return []

    q_norm = normalize_node_key(q)
    results = []
    for n in nodes:
        if isinstance(n, dict):
            node_id = n.get("nodeId", n.get("node_id", ""))
            remote_ip = n.get("remoteIp", n.get("remote_ip", ""))
            display_name = n.get("displayName", n.get("display_name", ""))
        else:
            node_id = n.node_id
            remote_ip = n.remote_ip
            display_name = n.display_name

        if node_id == q:
            results.append(n)
            continue
        if remote_ip and remote_ip == q:
            results.append(n)
            continue
        if display_name and normalize_node_key(display_name) == q_norm:
            results.append(n)
            continue
        if len(q) >= 6 and node_id.startswith(q):
            results.append(n)
            continue

    return results


# ─── node-list-parse.ts ───

def parse_node_list_response(data: list[dict[str, Any]]) -> list[NodeListEntry]:
    """Parse a raw node list response into NodeListEntry objects."""
    entries = []
    for item in data:
        if not isinstance(item, dict):
            continue
        entries.append(NodeListEntry(
            node_id=str(item.get("nodeId", item.get("id", ""))),
            display_name=str(item.get("displayName", item.get("name", ""))),
            remote_ip=str(item.get("remoteIp", item.get("ip", ""))),
            connected=bool(item.get("connected", False)),
            os=str(item.get("os", "")),
            hostname=str(item.get("hostname", "")),
            tags=item.get("tags", []),
        ))
    return entries


# ─── node-resolve.ts ───

def resolve_single_node(
    nodes: list[NodeListEntry | dict[str, Any]],
    query: str,
) -> tuple[NodeListEntry | dict[str, Any] | None, str | None]:
    """Resolve a single node from query. Returns (node, error)."""
    matches = resolve_node_matches(nodes, query)
    if not matches:
        known = ", ".join(
            (n.display_name or n.remote_ip or n.node_id) if isinstance(n, NodeListEntry)
            else (n.get("displayName") or n.get("remoteIp") or n.get("nodeId", ""))
            for n in nodes
        )
        return None, f"No node found matching '{query}'. Known: {known}"
    if len(matches) > 1:
        names = ", ".join(
            (n.display_name or n.node_id) if isinstance(n, NodeListEntry)
            else (n.get("displayName") or n.get("nodeId", ""))
            for n in matches
        )
        return None, f"Multiple nodes match '{query}': {names}"
    return matches[0], None

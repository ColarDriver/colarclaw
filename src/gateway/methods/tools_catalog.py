"""Gateway server methods — tools catalog handler.

Ported from bk/src/gateway/server-methods/tools-catalog.ts (167 lines).

Handles `tools.catalog` RPC method — lists available tools (core + plugin),
grouped into sections with profile association metadata.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Tool catalog types ───

PROFILE_OPTIONS = [
    {"id": "minimal", "label": "Minimal"},
    {"id": "coding", "label": "Coding"},
    {"id": "messaging", "label": "Messaging"},
    {"id": "full", "label": "Full"},
]


@dataclass
class ToolCatalogEntry:
    """A single tool in the catalog."""
    id: str = ""
    label: str = ""
    description: str = ""
    source: str = "core"  # "core" | "plugin"
    plugin_id: str | None = None
    optional: bool = False
    default_profiles: list[str] = field(default_factory=list)


@dataclass
class ToolCatalogGroup:
    """A group of related tools."""
    id: str = ""
    label: str = ""
    source: str = "core"  # "core" | "plugin"
    plugin_id: str | None = None
    tools: list[ToolCatalogEntry] = field(default_factory=list)


# ─── Core tool sections ───

# Simplified core tool sections; in production these come from agents/tool-catalog.ts
CORE_TOOL_SECTIONS = [
    ToolCatalogGroup(
        id="system",
        label="System",
        source="core",
        tools=[
            ToolCatalogEntry(id="bash", label="Bash", description="Execute shell commands",
                             default_profiles=["minimal", "coding", "full"]),
            ToolCatalogEntry(id="computer", label="Computer", description="Computer-use tool",
                             default_profiles=["full"]),
        ],
    ),
    ToolCatalogGroup(
        id="filesystem",
        label="File System",
        source="core",
        tools=[
            ToolCatalogEntry(id="read_file", label="Read File", description="Read file contents",
                             default_profiles=["minimal", "coding", "full"]),
            ToolCatalogEntry(id="write_file", label="Write File", description="Write to files",
                             default_profiles=["minimal", "coding", "full"]),
            ToolCatalogEntry(id="list_directory", label="List Directory",
                             description="List directory contents",
                             default_profiles=["minimal", "coding", "full"]),
        ],
    ),
    ToolCatalogGroup(
        id="web",
        label="Web",
        source="core",
        tools=[
            ToolCatalogEntry(id="web_search", label="Web Search",
                             description="Search the web",
                             default_profiles=["messaging", "full"]),
            ToolCatalogEntry(id="web_fetch", label="Web Fetch",
                             description="Fetch web page content",
                             default_profiles=["coding", "full"]),
        ],
    ),
    ToolCatalogGroup(
        id="messaging",
        label="Messaging",
        source="core",
        tools=[
            ToolCatalogEntry(id="send_message", label="Send Message",
                             description="Send a message to a channel",
                             default_profiles=["messaging", "full"]),
        ],
    ),
]


def list_core_tool_sections() -> list[ToolCatalogGroup]:
    """List all core tool sections."""
    return CORE_TOOL_SECTIONS


def resolve_core_tool_profiles(tool_id: str) -> list[str]:
    """Resolve which profiles include a given core tool."""
    for section in CORE_TOOL_SECTIONS:
        for tool in section.tools:
            if tool.id == tool_id:
                return tool.default_profiles
    return []


# ─── Plugin tool discovery ───

def build_plugin_groups(
    *,
    cfg: dict[str, Any],
    agent_id: str,
    existing_tool_names: set[str],
) -> list[ToolCatalogGroup]:
    """Build tool catalog groups from installed plugins.

    Discovers plugin tools, deduplicates against core tools,
    and organizes into groups by plugin ID.
    """
    # Plugin tool resolution depends on the plugin infrastructure
    # In production, this calls resolvePluginTools from plugins/tools
    groups: dict[str, ToolCatalogGroup] = {}

    plugins_cfg = cfg.get("plugins", {}) or {}
    tools_list = plugins_cfg.get("tools", [])
    if not isinstance(tools_list, list):
        return []

    for tool_raw in tools_list:
        if not isinstance(tool_raw, dict):
            continue
        tool_name = tool_raw.get("name", "")
        if not tool_name or tool_name in existing_tool_names:
            continue

        plugin_id = tool_raw.get("pluginId", "plugin")
        group_id = f"plugin:{plugin_id}"

        if group_id not in groups:
            groups[group_id] = ToolCatalogGroup(
                id=group_id,
                label=plugin_id,
                source="plugin",
                plugin_id=plugin_id,
            )

        groups[group_id].tools.append(ToolCatalogEntry(
            id=tool_name,
            label=tool_raw.get("label", tool_name),
            description=tool_raw.get("description", "Plugin tool"),
            source="plugin",
            plugin_id=plugin_id,
            optional=bool(tool_raw.get("optional", False)),
            default_profiles=[],
        ))

    # Sort tools within groups and groups by label
    result = list(groups.values())
    for group in result:
        group.tools.sort(key=lambda t: t.id)
    result.sort(key=lambda g: g.label)

    return result


def build_tools_catalog_response(
    *,
    cfg: dict[str, Any],
    agent_id: str = "",
    include_plugins: bool = True,
) -> dict[str, Any]:
    """Build the full tools.catalog response.

    Combines core tool sections with plugin tools,
    returning groups and profile metadata.
    """
    groups = list_core_tool_sections()

    if include_plugins:
        existing_names = set()
        for group in groups:
            for tool in group.tools:
                existing_names.add(tool.id)

        plugin_groups = build_plugin_groups(
            cfg=cfg,
            agent_id=agent_id,
            existing_tool_names=existing_names,
        )
        groups.extend(plugin_groups)

    return {
        "agentId": agent_id,
        "profiles": [{"id": p["id"], "label": p["label"]} for p in PROFILE_OPTIONS],
        "groups": [_group_to_dict(g) for g in groups],
    }


def _group_to_dict(group: ToolCatalogGroup) -> dict[str, Any]:
    """Serialize a ToolCatalogGroup to a dict."""
    result: dict[str, Any] = {
        "id": group.id,
        "label": group.label,
        "source": group.source,
        "tools": [_tool_to_dict(t) for t in group.tools],
    }
    if group.plugin_id:
        result["pluginId"] = group.plugin_id
    return result


def _tool_to_dict(tool: ToolCatalogEntry) -> dict[str, Any]:
    """Serialize a ToolCatalogEntry to a dict."""
    result: dict[str, Any] = {
        "id": tool.id,
        "label": tool.label,
        "description": tool.description,
        "source": tool.source,
        "defaultProfiles": tool.default_profiles,
    }
    if tool.plugin_id:
        result["pluginId"] = tool.plugin_id
    if tool.optional:
        result["optional"] = True
    return result

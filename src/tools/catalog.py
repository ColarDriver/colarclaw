"""Core tool catalog — ported from bk/src/agents/tool-catalog.ts.

Defines all recognized core tools, their profile membership,
section grouping, and group expansion logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ToolProfileId = Literal["minimal", "coding", "messaging", "full"]


@dataclass(frozen=True)
class CoreToolDefinition:
    id: str
    label: str
    description: str
    section_id: str
    profiles: tuple[ToolProfileId, ...]
    include_in_openclaw_group: bool = False


@dataclass(frozen=True)
class CoreToolSection:
    id: str
    label: str
    tools: list[dict[str, str]]


# ── Section ordering ───────────────────────────────────────────────────────

CORE_TOOL_SECTION_ORDER: list[dict[str, str]] = [
    {"id": "fs", "label": "Files"},
    {"id": "runtime", "label": "Runtime"},
    {"id": "web", "label": "Web"},
    {"id": "memory", "label": "Memory"},
    {"id": "sessions", "label": "Sessions"},
    {"id": "ui", "label": "UI"},
    {"id": "messaging", "label": "Messaging"},
    {"id": "automation", "label": "Automation"},
    {"id": "nodes", "label": "Nodes"},
    {"id": "agents", "label": "Agents"},
    {"id": "media", "label": "Media"},
]

# ── Tool definitions ──────────────────────────────────────────────────────

CORE_TOOL_DEFINITIONS: list[CoreToolDefinition] = [
    CoreToolDefinition("read", "read", "Read file contents", "fs", ("coding",)),
    CoreToolDefinition("write", "write", "Create or overwrite files", "fs", ("coding",)),
    CoreToolDefinition("edit", "edit", "Make precise edits", "fs", ("coding",)),
    CoreToolDefinition("apply_patch", "apply_patch", "Patch files (OpenAI)", "fs", ("coding",)),
    CoreToolDefinition("exec", "exec", "Run shell commands", "runtime", ("coding",)),
    CoreToolDefinition("process", "process", "Manage background processes", "runtime", ("coding",)),
    CoreToolDefinition("web_search", "web_search", "Search the web", "web", (), True),
    CoreToolDefinition("web_fetch", "web_fetch", "Fetch web content", "web", (), True),
    CoreToolDefinition("memory_search", "memory_search", "Semantic search", "memory", ("coding",), True),
    CoreToolDefinition("memory_get", "memory_get", "Read memory files", "memory", ("coding",), True),
    CoreToolDefinition("sessions_list", "sessions_list", "List sessions", "sessions", ("coding", "messaging"), True),
    CoreToolDefinition("sessions_history", "sessions_history", "Session history", "sessions", ("coding", "messaging"), True),
    CoreToolDefinition("sessions_send", "sessions_send", "Send to session", "sessions", ("coding", "messaging"), True),
    CoreToolDefinition("sessions_spawn", "sessions_spawn", "Spawn sub-agent", "sessions", ("coding",), True),
    CoreToolDefinition("subagents", "subagents", "Manage sub-agents", "sessions", ("coding",), True),
    CoreToolDefinition("session_status", "session_status", "Session status", "sessions", ("minimal", "coding", "messaging"), True),
    CoreToolDefinition("browser", "browser", "Control web browser", "ui", (), True),
    CoreToolDefinition("canvas", "canvas", "Control canvases", "ui", (), True),
    CoreToolDefinition("message", "message", "Send messages", "messaging", ("messaging",), True),
    CoreToolDefinition("cron", "cron", "Schedule tasks", "automation", ("coding",), True),
    CoreToolDefinition("gateway", "gateway", "Gateway control", "automation", (), True),
    CoreToolDefinition("nodes", "nodes", "Nodes + devices", "nodes", (), True),
    CoreToolDefinition("agents_list", "agents_list", "List agents", "agents", (), True),
    CoreToolDefinition("image", "image", "Image understanding", "media", ("coding",), True),
    CoreToolDefinition("tts", "tts", "Text-to-speech conversion", "media", (), True),
]

_CORE_TOOL_BY_ID: dict[str, CoreToolDefinition] = {
    tool.id: tool for tool in CORE_TOOL_DEFINITIONS
}


# ── Profile policies ──────────────────────────────────────────────────────

def _list_core_tool_ids_for_profile(profile: ToolProfileId) -> list[str]:
    return [tool.id for tool in CORE_TOOL_DEFINITIONS if profile in tool.profiles]


ToolProfilePolicy = dict[str, list[str] | None]

CORE_TOOL_PROFILES: dict[ToolProfileId, ToolProfilePolicy] = {
    "minimal": {"allow": _list_core_tool_ids_for_profile("minimal")},
    "coding": {"allow": _list_core_tool_ids_for_profile("coding")},
    "messaging": {"allow": _list_core_tool_ids_for_profile("messaging")},
    "full": {},
}


def _build_core_tool_group_map() -> dict[str, list[str]]:
    section_map: dict[str, list[str]] = {}
    for tool in CORE_TOOL_DEFINITIONS:
        group_id = f"group:{tool.section_id}"
        section_map.setdefault(group_id, []).append(tool.id)

    openclaw_tools = [
        tool.id for tool in CORE_TOOL_DEFINITIONS
        if tool.include_in_openclaw_group
    ]
    result = {"group:openclaw": openclaw_tools}
    result.update(section_map)
    return result


CORE_TOOL_GROUPS: dict[str, list[str]] = _build_core_tool_group_map()


# ── Public API ─────────────────────────────────────────────────────────────

PROFILE_OPTIONS: list[dict[str, str]] = [
    {"id": "minimal", "label": "Minimal"},
    {"id": "coding", "label": "Coding"},
    {"id": "messaging", "label": "Messaging"},
    {"id": "full", "label": "Full"},
]


def resolve_core_tool_profile_policy(profile: str | None = None) -> ToolProfilePolicy | None:
    if not profile:
        return None
    resolved = CORE_TOOL_PROFILES.get(profile)  # type: ignore[arg-type]
    if resolved is None:
        return None
    if not resolved.get("allow") and not resolved.get("deny"):
        return None
    return {
        "allow": list(resolved["allow"]) if resolved.get("allow") else None,
        "deny": list(resolved["deny"]) if resolved.get("deny") else None,
    }


def list_core_tool_sections() -> list[CoreToolSection]:
    result: list[CoreToolSection] = []
    for section in CORE_TOOL_SECTION_ORDER:
        tools = [
            {"id": tool.id, "label": tool.label, "description": tool.description}
            for tool in CORE_TOOL_DEFINITIONS
            if tool.section_id == section["id"]
        ]
        if tools:
            result.append(CoreToolSection(
                id=section["id"],
                label=section["label"],
                tools=tools,
            ))
    return result


def resolve_core_tool_profiles(tool_id: str) -> list[ToolProfileId]:
    tool = _CORE_TOOL_BY_ID.get(tool_id)
    if not tool:
        return []
    return list(tool.profiles)


def is_known_core_tool_id(tool_id: str) -> bool:
    return tool_id in _CORE_TOOL_BY_ID

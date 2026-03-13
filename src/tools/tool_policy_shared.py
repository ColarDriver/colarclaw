"""Tool policy shared helpers — ported from bk/src/agents/tool-policy-shared.ts and tool-policy.ts.

Provides tool name normalization, tool group expansion, allow/deny list
resolution, owner-only policy, and plugin-group expansion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .catalog import CORE_TOOL_GROUPS, resolve_core_tool_profile_policy

# ── Tool name aliases ──────────────────────────────────────────────────────

TOOL_NAME_ALIASES: dict[str, str] = {
    "bash": "exec",
    "apply-patch": "apply_patch",
}

TOOL_GROUPS: dict[str, list[str]] = {**CORE_TOOL_GROUPS}

OWNER_ONLY_TOOL_NAME_FALLBACKS: set[str] = {"whatsapp_login", "cron", "gateway"}


# ── Name normalization ─────────────────────────────────────────────────────

def normalize_tool_name(name: str) -> str:
    normalized = name.strip().lower()
    return TOOL_NAME_ALIASES.get(normalized, normalized)


def normalize_tool_list(tools: list[str] | None) -> list[str]:
    if not tools:
        return []
    return [n for n in (normalize_tool_name(t) for t in tools) if n]


def expand_tool_groups(tools: list[str] | None) -> list[str]:
    normalized = normalize_tool_list(tools)
    expanded: list[str] = []
    for value in normalized:
        group = TOOL_GROUPS.get(value)
        if group:
            expanded.extend(group)
        else:
            expanded.append(value)
    return list(dict.fromkeys(expanded))  # unique, preserving order


def resolve_tool_profile_policy(profile: str | None = None) -> dict[str, Any] | None:
    return resolve_core_tool_profile_policy(profile)


# ── Owner-only policy ─────────────────────────────────────────────────────

def is_owner_only_tool_name(name: str) -> bool:
    return normalize_tool_name(name) in OWNER_ONLY_TOOL_NAME_FALLBACKS


def is_owner_only_tool(tool: dict[str, Any]) -> bool:
    if tool.get("ownerOnly") is True:
        return True
    return is_owner_only_tool_name(tool.get("name", ""))


def apply_owner_only_tool_policy(
    tools: list[dict[str, Any]],
    sender_is_owner: bool,
) -> list[dict[str, Any]]:
    """Filter/wrap tools based on owner-only policy."""
    result: list[dict[str, Any]] = []
    for tool in tools:
        if not is_owner_only_tool(tool):
            result.append(tool)
            continue
        if sender_is_owner:
            result.append(tool)
        # non-owner senders: tool is filtered out
    return result


# ── Allowlist resolution ───────────────────────────────────────────────────

@dataclass
class ToolPolicyLike:
    allow: list[str] | None = None
    deny: list[str] | None = None


@dataclass
class PluginToolGroups:
    all: list[str] = field(default_factory=list)
    by_plugin: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class AllowlistResolution:
    policy: ToolPolicyLike | None = None
    unknown_allowlist: list[str] = field(default_factory=list)
    stripped_allowlist: bool = False


def collect_explicit_allowlist(policies: list[ToolPolicyLike | None]) -> list[str]:
    entries: list[str] = []
    for policy in policies:
        if policy is None or policy.allow is None:
            continue
        for value in policy.allow:
            trimmed = value.strip()
            if trimmed:
                entries.append(trimmed)
    return entries


def build_plugin_tool_groups(
    tools: list[dict[str, Any]],
    tool_meta_fn: Any,
) -> PluginToolGroups:
    """Build plugin tool groups from a list of tools and a metadata extractor."""
    all_names: list[str] = []
    by_plugin: dict[str, list[str]] = {}

    for tool in tools:
        meta = tool_meta_fn(tool)
        if meta is None:
            continue
        name = normalize_tool_name(tool.get("name", ""))
        all_names.append(name)
        plugin_id = meta.get("pluginId", "").lower()
        by_plugin.setdefault(plugin_id, []).append(name)

    return PluginToolGroups(all=all_names, by_plugin=by_plugin)


def expand_plugin_groups(
    tools_list: list[str] | None,
    groups: PluginToolGroups,
) -> list[str] | None:
    if not tools_list:
        return tools_list
    expanded: list[str] = []
    for entry in tools_list:
        normalized = normalize_tool_name(entry)
        if normalized == "group:plugins":
            if groups.all:
                expanded.extend(groups.all)
            else:
                expanded.append(normalized)
            continue
        plugin_tools = groups.by_plugin.get(normalized)
        if plugin_tools:
            expanded.extend(plugin_tools)
            continue
        expanded.append(normalized)
    return list(dict.fromkeys(expanded))


def expand_policy_with_plugin_groups(
    policy: ToolPolicyLike | None,
    groups: PluginToolGroups,
) -> ToolPolicyLike | None:
    if policy is None:
        return None
    return ToolPolicyLike(
        allow=expand_plugin_groups(policy.allow, groups),
        deny=expand_plugin_groups(policy.deny, groups),
    )


def strip_plugin_only_allowlist(
    policy: ToolPolicyLike | None,
    groups: PluginToolGroups,
    core_tools: set[str],
) -> AllowlistResolution:
    """Strip allowlists that only reference plugin tools to avoid disabling core tools."""
    if policy is None or not policy.allow:
        return AllowlistResolution(policy=policy)

    normalized = normalize_tool_list(policy.allow)
    if not normalized:
        return AllowlistResolution(policy=policy)

    plugin_ids = set(groups.by_plugin.keys())
    plugin_tools = set(groups.all)
    unknown_allowlist: list[str] = []
    has_core_entry = False

    for entry in normalized:
        if entry == "*":
            has_core_entry = True
            continue
        is_plugin_entry = (
            entry == "group:plugins"
            or entry in plugin_ids
            or entry in plugin_tools
        )
        expanded = expand_tool_groups([entry])
        is_core_entry = any(tool in core_tools for tool in expanded)
        if is_core_entry:
            has_core_entry = True
        if not is_core_entry and not is_plugin_entry:
            unknown_allowlist.append(entry)

    stripped = not has_core_entry
    return AllowlistResolution(
        policy=ToolPolicyLike(allow=None, deny=policy.deny) if stripped else policy,
        unknown_allowlist=list(dict.fromkeys(unknown_allowlist)),
        stripped_allowlist=stripped,
    )


def merge_also_allow_policy(
    policy: ToolPolicyLike | None,
    also_allow: list[str] | None = None,
) -> ToolPolicyLike | None:
    if policy is None or not policy.allow or not also_allow:
        return policy
    merged = list(dict.fromkeys(policy.allow + also_allow))
    return ToolPolicyLike(allow=merged, deny=policy.deny)

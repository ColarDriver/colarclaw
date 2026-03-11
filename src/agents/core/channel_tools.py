"""Channel tools — ported from bk/src/agents/channel-tools.ts.

Channel-level tool listing, message action enumeration, and prompt hints.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("openclaw.agents.channel_tools")

ChannelMessageActionName = str
_logged_list_action_errors: set[str] = set()


def list_channel_supported_actions(
    cfg: Any | None = None,
    channel: str | None = None,
) -> list[ChannelMessageActionName]:
    """Get supported message actions for a specific channel."""
    if not channel:
        return []
    try:
        from ..channels.plugins import get_channel_plugin
        plugin = get_channel_plugin(channel)
        if not plugin or not hasattr(plugin, "actions") or not plugin.actions:
            return []
        list_actions = getattr(plugin.actions, "list_actions", None)
        if not list_actions:
            return []
        return _run_plugin_list_actions(plugin, cfg)
    except (ImportError, Exception):
        return []


def list_all_channel_supported_actions(
    cfg: Any | None = None,
) -> list[ChannelMessageActionName]:
    """Get all supported message actions across all channels."""
    actions: set[ChannelMessageActionName] = set()
    try:
        from ..channels.plugins import list_channel_plugins
        for plugin in list_channel_plugins():
            if not hasattr(plugin, "actions") or not plugin.actions:
                continue
            list_actions = getattr(plugin.actions, "list_actions", None)
            if not list_actions:
                continue
            channel_actions = _run_plugin_list_actions(plugin, cfg)
            actions.update(channel_actions)
    except (ImportError, Exception):
        pass
    return list(actions)


def list_channel_agent_tools(cfg: Any | None = None) -> list[Any]:
    """Aggregate channel-owned agent tools (login, etc.)."""
    tools: list[Any] = []
    try:
        from ..channels.plugins import list_channel_plugins
        for plugin in list_channel_plugins():
            entry = getattr(plugin, "agent_tools", None)
            if entry is None:
                continue
            resolved = entry({"cfg": cfg}) if callable(entry) else entry
            if isinstance(resolved, list):
                tools.extend(resolved)
    except (ImportError, Exception):
        pass
    return tools


def resolve_channel_message_tool_hints(
    cfg: Any | None = None,
    channel: str | None = None,
    account_id: str | None = None,
) -> list[str]:
    """Resolve channel-specific message tool hints."""
    if not channel:
        return []
    try:
        from ..channels.registry import normalize_any_channel_id
        from ..channels.dock import get_channel_dock
        channel_id = normalize_any_channel_id(channel)
        if not channel_id:
            return []
        dock = get_channel_dock(channel_id)
        if not dock:
            return []
        resolve = getattr(getattr(dock, "agent_prompt", None), "message_tool_hints", None)
        if not resolve:
            return []
        hints = resolve({"cfg": cfg, "account_id": account_id}) or []
        return [h.strip() for h in hints if h.strip()]
    except (ImportError, Exception):
        return []


def _run_plugin_list_actions(plugin: Any, cfg: Any | None) -> list[ChannelMessageActionName]:
    list_actions = getattr(plugin.actions, "list_actions", None)
    if not list_actions:
        return []
    try:
        listed = list_actions({"cfg": cfg or {}})
        return listed if isinstance(listed, list) else []
    except Exception as err:
        _log_list_actions_error(getattr(plugin, "id", "unknown"), err)
        return []


def _log_list_actions_error(plugin_id: str, err: Exception) -> None:
    message = str(err)
    key = f"{plugin_id}:{message}"
    if key in _logged_list_action_errors:
        return
    _logged_list_action_errors.add(key)
    log.error("[channel-tools] %s.actions.list_actions failed: %s", plugin_id, message)


def _reset_logged_list_action_errors() -> None:
    """For testing."""
    _logged_list_action_errors.clear()

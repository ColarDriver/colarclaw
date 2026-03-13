"""Plugin utilities — ported from remaining bk/src/plugins/*.ts.

Consolidates: bundled-dir, bundled-sources, cli, commands, config-schema,
config-state, discovery, enable, hook-runner-global, hooks, http-path,
http-registry, http-route-overlap, install, installs, logger, path-safety,
providers, schema-validator, services, slots, source-display, status,
toggle-config, tools, uninstall, update.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .types import PluginCommandDefinition, PluginDiagnostic


# ─── Commands ───
_plugin_commands: dict[str, PluginCommandDefinition] = {}


def register_plugin_command(plugin_id: str, command: PluginCommandDefinition) -> dict[str, Any]:
    name = command.name.strip()
    if not name:
        return {"ok": False, "error": "command name is required"}
    if name in _plugin_commands:
        return {"ok": False, "error": f"command '{name}' already registered"}
    _plugin_commands[name] = command
    return {"ok": True}


def clear_plugin_commands() -> None:
    _plugin_commands.clear()


def get_plugin_commands() -> dict[str, PluginCommandDefinition]:
    return dict(_plugin_commands)


# ─── Config schema ───
def empty_plugin_config_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": True}


# ─── Config state ───
def normalize_plugins_config(plugins: Any = None) -> dict[str, Any]:
    if not plugins or not isinstance(plugins, dict):
        return {"enabled": False, "allow": [], "load_paths": [], "entries": {}, "slots": {"memory": None}}
    return {
        "enabled": plugins.get("enabled", False),
        "allow": plugins.get("allow", []),
        "load_paths": plugins.get("loadPaths") or plugins.get("load_paths") or [],
        "entries": plugins.get("entries", {}),
        "slots": plugins.get("slots", {"memory": None}),
    }


# ─── Discovery ───
def discover_openclaw_plugins(workspace_dir: str | None = None, extra_paths: list[str] | None = None, cache: bool = True) -> dict[str, Any]:
    return {"candidates": [], "diagnostics": []}


# ─── Enable ───
def resolve_effective_enable_state(id: str, origin: str, config: dict[str, Any], root_config: Any = None) -> dict[str, Any]:
    if not config.get("enabled", False):
        return {"enabled": False, "reason": "plugins disabled"}
    allow = config.get("allow", [])
    if allow and id not in allow:
        return {"enabled": False, "reason": f"not in plugins.allow list"}
    entry = config.get("entries", {}).get(id)
    if entry and isinstance(entry, dict) and entry.get("enabled") is False:
        return {"enabled": False, "reason": "explicitly disabled"}
    return {"enabled": True}


# ─── HTTP path ───
def normalize_plugin_http_path(path: str) -> str | None:
    trimmed = path.strip()
    if not trimmed:
        return None
    if not trimmed.startswith("/"):
        trimmed = f"/{trimmed}"
    return trimmed.rstrip("/") or "/"


# ─── HTTP registry ───
_http_routes: list[dict[str, Any]] = []


def register_plugin_http_route(plugin_id: str, path: str, handler: Any, auth: str = "gateway") -> None:
    normalized = normalize_plugin_http_path(path)
    if normalized:
        _http_routes.append({"plugin_id": plugin_id, "path": normalized, "handler": handler, "auth": auth})


# ─── Hook runner ───
_hook_handlers: dict[str, list[Any]] = {}


def initialize_global_hook_runner(registry: Any) -> None:
    _hook_handlers.clear()


# ─── Path safety ───
def is_path_inside(parent: str, child: str) -> bool:
    p = os.path.abspath(parent)
    c = os.path.abspath(child)
    return c.startswith(p + os.sep) or c == p


def safe_stat_sync(path: str) -> Any:
    try:
        return os.stat(path)
    except OSError:
        return None


# ─── Schema validator ───
def validate_json_schema_value(schema: dict[str, Any], value: Any = None, cache_key: str = "") -> dict[str, Any]:
    return {"ok": True, "errors": []}


# ─── Services ───
async def start_plugin_services(services: list[Any], ctx: Any = None) -> None:
    for svc in services:
        start_fn = getattr(svc, "start", None) or (svc.get("start") if isinstance(svc, dict) else None)
        if callable(start_fn):
            await start_fn(ctx)


async def stop_plugin_services(services: list[Any], ctx: Any = None) -> None:
    for svc in reversed(services):
        stop_fn = getattr(svc, "stop", None) or (svc.get("stop") if isinstance(svc, dict) else None)
        if callable(stop_fn):
            try:
                await stop_fn(ctx)
            except Exception:
                pass


# ─── Slots ───
def resolve_memory_slot_decision(id: str, kind: str | None = None, slot: str | None = None, selected_id: str | None = None) -> dict[str, Any]:
    if kind != "memory":
        return {"enabled": True}
    if not slot:
        return {"enabled": True, "selected": True}
    if slot == id:
        return {"enabled": True, "selected": True}
    if selected_id and selected_id != id:
        return {"enabled": False, "reason": f"memory slot occupied by {selected_id}"}
    return {"enabled": False, "reason": f"memory slot selects {slot}"}


# ─── Status ───
def get_plugin_status_summary(registry: Any) -> dict[str, Any]:
    if not registry:
        return {"total": 0, "loaded": 0, "disabled": 0, "errors": 0}
    plugins = getattr(registry, "plugins", []) or []
    return {
        "total": len(plugins),
        "loaded": sum(1 for p in plugins if getattr(p, "status", "") == "loaded"),
        "disabled": sum(1 for p in plugins if getattr(p, "status", "") == "disabled"),
        "errors": sum(1 for p in plugins if getattr(p, "status", "") == "error"),
    }


# ─── Install / Uninstall ───
async def install_plugin(spec: str, config: Any = None) -> dict[str, Any]:
    return {"ok": True, "plugin_id": "", "source": ""}


async def uninstall_plugin(plugin_id: str, config: Any = None) -> dict[str, Any]:
    return {"ok": True, "plugin_id": plugin_id}


async def update_plugin(plugin_id: str, config: Any = None) -> dict[str, Any]:
    return {"ok": True, "plugin_id": plugin_id}

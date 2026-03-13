"""Plugin loader — ported from bk/src/plugins/loader.ts.

Plugin discovery, loading, and activation pipeline.
"""
from __future__ import annotations

import importlib
import os
from typing import Any

from .manifest import load_plugin_manifest
from .registry import PluginRecord, PluginRegistry, create_empty_plugin_registry, create_plugin_registry
from .types import PluginDiagnostic, PluginLogger


def create_plugin_record(
    id: str, name: str | None = None, source: str = "", origin: str = "bundled",
    workspace_dir: str | None = None, enabled: bool = True, config_schema: bool = False,
    **kwargs: Any,
) -> PluginRecord:
    return PluginRecord(
        id=id, name=name or id, source=source, origin=origin,
        workspace_dir=workspace_dir, enabled=enabled,
        status="loaded" if enabled else "disabled",
        config_schema=config_schema, **kwargs,
    )


def discover_plugins(workspace_dir: str | None = None, extra_paths: list[str] | None = None) -> list[dict[str, Any]]:
    """Discover available plugins from workspace and load paths."""
    candidates: list[dict[str, Any]] = []
    search_dirs: list[str] = []
    if workspace_dir:
        plugins_dir = os.path.join(workspace_dir, "plugins")
        if os.path.isdir(plugins_dir):
            search_dirs.append(plugins_dir)
    if extra_paths:
        search_dirs.extend(p for p in extra_paths if os.path.isdir(p))
    for search_dir in search_dirs:
        try:
            for entry in os.scandir(search_dir):
                if entry.is_dir():
                    manifest_result = load_plugin_manifest(entry.path)
                    if manifest_result.ok and manifest_result.manifest:
                        candidates.append({
                            "id": manifest_result.manifest.id,
                            "root_dir": entry.path,
                            "source": os.path.join(entry.path, "index.py"),
                            "origin": "workspace" if workspace_dir and entry.path.startswith(workspace_dir) else "global",
                            "workspace_dir": workspace_dir,
                        })
        except OSError:
            pass
    return candidates


def load_openclaw_plugins(
    config: Any = None,
    workspace_dir: str | None = None,
    logger: Any = None,
    extra_paths: list[str] | None = None,
) -> PluginRegistry:
    """Load and register all discovered plugins."""
    registry, create_api = create_plugin_registry(logger=logger)
    candidates = discover_plugins(workspace_dir=workspace_dir, extra_paths=extra_paths)
    seen_ids: set[str] = set()
    for candidate in candidates:
        plugin_id = candidate["id"]
        if plugin_id in seen_ids:
            continue
        seen_ids.add(plugin_id)
        record = create_plugin_record(
            id=plugin_id, source=candidate.get("source", ""),
            origin=candidate.get("origin", "workspace"),
            workspace_dir=candidate.get("workspace_dir"),
            enabled=True, config_schema=True,
        )
        try:
            source = candidate.get("source", "")
            if source.endswith(".py") and os.path.isfile(source):
                spec = importlib.util.spec_from_file_location(plugin_id, source)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    register_fn = getattr(mod, "register", None) or getattr(mod, "activate", None)
                    if register_fn:
                        api = create_api(record, config=config)
                        register_fn(api)
            record.status = "loaded"
        except Exception as e:
            record.status = "error"
            record.error = str(e)
            registry.diagnostics.append(PluginDiagnostic(level="error", plugin_id=record.id, source=record.source, message=f"failed to load: {e}"))
        registry.plugins.append(record)
    return registry

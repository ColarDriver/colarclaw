"""Plugin manifest — ported from bk/src/plugins/manifest.ts + manifest-registry.ts.

Plugin manifest loading and validation.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from .types import PluginConfigUiHint, PluginKind

PLUGIN_MANIFEST_FILENAME = "openclaw.plugin.json"
PLUGIN_MANIFEST_FILENAMES = [PLUGIN_MANIFEST_FILENAME]


@dataclass
class PluginManifest:
    id: str = ""
    config_schema: dict[str, Any] = field(default_factory=dict)
    kind: PluginKind | None = None
    channels: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    name: str | None = None
    description: str | None = None
    version: str | None = None
    ui_hints: dict[str, Any] | None = None


@dataclass
class PluginManifestLoadResult:
    ok: bool = False
    manifest: PluginManifest | None = None
    manifest_path: str = ""
    error: str | None = None


def resolve_plugin_manifest_path(root_dir: str) -> str:
    for filename in PLUGIN_MANIFEST_FILENAMES:
        candidate = os.path.join(root_dir, filename)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(root_dir, PLUGIN_MANIFEST_FILENAME)


def load_plugin_manifest(root_dir: str) -> PluginManifestLoadResult:
    manifest_path = resolve_plugin_manifest_path(root_dir)
    if not os.path.isfile(manifest_path):
        return PluginManifestLoadResult(ok=False, manifest_path=manifest_path, error=f"plugin manifest not found: {manifest_path}")
    try:
        with open(manifest_path, "r") as f:
            raw = json.load(f)
    except Exception as e:
        return PluginManifestLoadResult(ok=False, manifest_path=manifest_path, error=f"failed to parse plugin manifest: {e}")
    if not isinstance(raw, dict):
        return PluginManifestLoadResult(ok=False, manifest_path=manifest_path, error="plugin manifest must be an object")
    pid = str(raw.get("id", "")).strip()
    if not pid:
        return PluginManifestLoadResult(ok=False, manifest_path=manifest_path, error="plugin manifest requires id")
    config_schema = raw.get("configSchema") or raw.get("config_schema")
    if not isinstance(config_schema, dict):
        return PluginManifestLoadResult(ok=False, manifest_path=manifest_path, error="plugin manifest requires configSchema")

    def normalize_string_list(val: Any) -> list[str]:
        if not isinstance(val, list):
            return []
        return [str(e).strip() for e in val if isinstance(e, str) and e.strip()]

    manifest = PluginManifest(
        id=pid, config_schema=config_schema,
        kind=raw.get("kind") if raw.get("kind") in ("memory", "context-engine") else None,
        channels=normalize_string_list(raw.get("channels")),
        providers=normalize_string_list(raw.get("providers")),
        skills=normalize_string_list(raw.get("skills")),
        name=str(raw.get("name", "")).strip() or None,
        description=str(raw.get("description", "")).strip() or None,
        version=str(raw.get("version", "")).strip() or None,
        ui_hints=raw.get("uiHints") if isinstance(raw.get("uiHints"), dict) else None,
    )
    return PluginManifestLoadResult(ok=True, manifest=manifest, manifest_path=manifest_path)


# Package manifest
@dataclass
class PluginPackageChannel:
    id: str | None = None
    label: str | None = None
    docs_path: str | None = None
    blurb: str | None = None
    order: int | None = None
    aliases: list[str] | None = None


@dataclass
class PluginPackageInstall:
    npm_spec: str | None = None
    local_path: str | None = None


def get_package_manifest_metadata(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not manifest:
        return None
    return manifest.get("openclaw")


def resolve_package_extension_entries(manifest: dict[str, Any] | None) -> dict[str, Any]:
    meta = get_package_manifest_metadata(manifest)
    if not meta:
        return {"status": "missing", "entries": []}
    raw = meta.get("extensions")
    if not isinstance(raw, list):
        return {"status": "missing", "entries": []}
    entries = [str(e).strip() for e in raw if isinstance(e, str) and e.strip()]
    if not entries:
        return {"status": "empty", "entries": []}
    return {"status": "ok", "entries": entries}

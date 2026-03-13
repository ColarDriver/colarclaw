"""Shared frontmatter — ported from bk/src/shared/frontmatter.ts.

Frontmatter parsing, manifest block resolution, and install spec parsing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .string_normalization import normalize_string_entries


# ─── frontmatter helpers ───

def normalize_string_list(value: Any) -> list[str]:
    """Normalize input to a list of trimmed non-empty strings."""
    if not value:
        return []
    if isinstance(value, list):
        return [s for v in value if (s := str(v).strip())]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def get_frontmatter_string(
    frontmatter: dict[str, Any],
    key: str,
) -> str | None:
    raw = frontmatter.get(key)
    return raw if isinstance(raw, str) else None


def parse_frontmatter_bool(value: str | None, fallback: bool) -> bool:
    if value is None:
        return fallback
    lower = value.strip().lower()
    if lower in ("true", "1", "yes", "on"):
        return True
    if lower in ("false", "0", "no", "off"):
        return False
    return fallback


# ─── manifest block ───

MANIFEST_KEY = "openclaw"
LEGACY_MANIFEST_KEYS = ["clawd", "clawdbot"]


def resolve_manifest_block(
    frontmatter: dict[str, Any],
    key: str = "metadata",
) -> dict[str, Any] | None:
    """Resolve the OpenClaw manifest block from frontmatter."""
    raw = get_frontmatter_string(frontmatter, key)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if not parsed or not isinstance(parsed, dict):
            return None
        for mkey in [MANIFEST_KEY, *LEGACY_MANIFEST_KEYS]:
            candidate = parsed.get(mkey)
            if candidate and isinstance(candidate, dict):
                return candidate
        return None
    except (json.JSONDecodeError, TypeError):
        return None


# ─── manifest requires ───

@dataclass
class ManifestRequires:
    bins: list[str] = field(default_factory=list)
    any_bins: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    config: list[str] = field(default_factory=list)


def resolve_manifest_requires(
    metadata_obj: dict[str, Any],
) -> ManifestRequires | None:
    requires_raw = metadata_obj.get("requires")
    if not isinstance(requires_raw, dict):
        return None
    return ManifestRequires(
        bins=normalize_string_list(requires_raw.get("bins")),
        any_bins=normalize_string_list(requires_raw.get("anyBins")),
        env=normalize_string_list(requires_raw.get("env")),
        config=normalize_string_list(requires_raw.get("config")),
    )


def resolve_manifest_os(metadata_obj: dict[str, Any]) -> list[str]:
    return normalize_string_list(metadata_obj.get("os"))


# ─── manifest install ───

@dataclass
class ManifestInstallBase:
    raw: dict[str, Any] = field(default_factory=dict)
    kind: str = ""
    id: str | None = None
    label: str | None = None
    bins: list[str] | None = None


def parse_manifest_install_base(
    input_val: Any,
    allowed_kinds: list[str] | tuple[str, ...],
) -> ManifestInstallBase | None:
    if not input_val or not isinstance(input_val, dict):
        return None
    kind_raw = input_val.get("kind") or input_val.get("type") or ""
    kind = str(kind_raw).strip().lower()
    if kind not in allowed_kinds:
        return None
    spec = ManifestInstallBase(raw=input_val, kind=kind)
    if isinstance(input_val.get("id"), str):
        spec.id = input_val["id"]
    if isinstance(input_val.get("label"), str):
        spec.label = input_val["label"]
    bins = normalize_string_list(input_val.get("bins"))
    if bins:
        spec.bins = bins
    return spec


def resolve_manifest_install(
    metadata_obj: dict[str, Any],
    parse_install_spec: Any,
) -> list[Any]:
    install_raw = metadata_obj.get("install", [])
    if not isinstance(install_raw, list):
        return []
    results = []
    for entry in install_raw:
        parsed = parse_install_spec(entry)
        if parsed:
            results.append(parsed)
    return results

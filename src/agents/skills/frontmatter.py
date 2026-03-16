"""Skill frontmatter parser for ColarCore — based on openclaw/src/agents/skills/frontmatter.ts.

Parses YAML frontmatter from SKILL.md files, including the JSON metadata
block that contains the ``openclaw`` key with emoji, requires, install, etc.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .types import ColarCoreSkillMetadata, SkillFrontmatter, SkillInstallSpec

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_skill_frontmatter(content: str) -> tuple[SkillFrontmatter | None, str]:
    """Parse YAML frontmatter from a skill file.

    Returns a tuple of (frontmatter, body_text).
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None, content

    frontmatter_text = match.group(1)
    body = content[match.end() :]

    fm = SkillFrontmatter()

    # Extract simple key-value pairs
    for line in frontmatter_text.splitlines():
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip().lower()
        value = value.strip()

        if key == "name":
            fm.name = value.strip("'\"")
        elif key == "description":
            # Handle quoted descriptions (possibly multi-line via a single-line quote)
            if value.startswith('"') and value.endswith('"'):
                fm.description = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                fm.description = value[1:-1]
            else:
                fm.description = value
        elif key == "homepage":
            fm.homepage = value.strip("'\"")
        elif key == "enabled":
            fm.enabled = value.lower() not in ("false", "0", "no")
        elif key == "user-invocable":
            fm.user_invocable = value.lower() in ("true", "1", "yes")

    # Parse metadata JSON block
    oc_meta = _parse_metadata_block(frontmatter_text)
    if oc_meta:
        fm.metadata = oc_meta
        # Propagate homepage from metadata if not already set
        if oc_meta.homepage and not fm.homepage:
            fm.homepage = oc_meta.homepage

    return fm, body


def _parse_metadata_block(fm_text: str) -> ColarCoreSkillMetadata | None:
    """Extract and parse the JSON metadata block from frontmatter text."""
    # Multi-line metadata: metadata:\n  { ... }
    metadata_match = re.search(r"metadata:\s*\n?\s*(\{.*)", fm_text, re.DOTALL)
    if metadata_match:
        json_text = metadata_match.group(1).strip()
        parsed = _try_parse_json(json_text)
        if parsed is not None:
            return _build_metadata(parsed)

    # Single-line metadata: metadata: { ... }
    for line in fm_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("metadata:"):
            json_part = stripped[len("metadata:") :].strip()
            if json_part.startswith("{"):
                parsed = _try_parse_json(json_part)
                if parsed is not None:
                    return _build_metadata(parsed)
            break

    return None


def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Attempt to parse JSON, with a cleanup fallback for JSON5 trailing commas."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


def _as_str_list(value: Any) -> list[str]:
    """Coerce value to a list of non-empty strings."""
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str) and v.strip()]
    return []


def _build_metadata(parsed: dict[str, Any]) -> ColarCoreSkillMetadata:
    """Build a ``ColarCoreSkillMetadata`` from a parsed JSON metadata dict."""
    oc: dict[str, Any] = {}
    if isinstance(parsed, dict):
        oc = parsed.get("openclaw", {})
        if not isinstance(oc, dict):
            oc = {}

    requires = oc.get("requires", {})
    if not isinstance(requires, dict):
        requires = {}

    install_specs: list[SkillInstallSpec] = []
    raw_install = oc.get("install")
    if isinstance(raw_install, list):
        for i, item in enumerate(raw_install):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "")).strip()
            if not kind:
                continue
            opt_id = str(item.get("id", f"{kind}-{i}")).strip()
            label = str(item.get("label", "")).strip()
            bins = _as_str_list(item.get("bins"))

            # Generate label if missing
            if not label:
                if kind == "brew" and item.get("formula"):
                    label = f"Install {item['formula']} (brew)"
                elif kind == "node" and item.get("package"):
                    label = f"Install {item['package']} (npm)"
                elif kind == "go" and item.get("module"):
                    label = f"Install {item['module']} (go)"
                elif kind == "uv" and item.get("package"):
                    label = f"Install {item['package']} (uv)"
                else:
                    label = f"Install ({kind})"

            install_specs.append(
                SkillInstallSpec(
                    id=opt_id,
                    kind=kind,
                    label=label,
                    bins=bins,
                    os=_as_str_list(item.get("os")),
                    formula=str(item.get("formula", "")),
                    package=str(item.get("package", "")),
                    module=str(item.get("module", "")),
                    url=str(item.get("url", "")),
                )
            )

    return ColarCoreSkillMetadata(
        always=bool(oc.get("always", False)),
        skill_key=str(oc.get("skillKey", "")),
        primary_env=str(oc.get("primaryEnv", "")),
        emoji=str(oc.get("emoji", "")),
        homepage=str(oc.get("homepage", "")),
        os=_as_str_list(oc.get("os")),
        required_bins=_as_str_list(requires.get("bins")),
        required_any_bins=_as_str_list(requires.get("anyBins")),
        required_env=_as_str_list(requires.get("env")),
        required_config=_as_str_list(requires.get("config")),
        install=install_specs,
    )

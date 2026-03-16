"""Skill status & catalog — ported from openclaw/src/agents/skills-status.ts.

Provides ``SkillCatalog`` (discovers and caches skill entries from SKILL.md files)
and helpers for computing missing requirements that the gateway status API needs.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from .frontmatter import parse_skill_frontmatter
from .types import SkillEntry, SkillInstallOption

_SKILL_HEADING = re.compile(r"^#\s+(.+)$")
_SKILL_DESC = re.compile(r"^>\s*(.+)$")


class SkillCatalog:
    """Discovers and caches skill entries from a skills root directory."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._entries: dict[str, SkillEntry] = {}

    def reload(self) -> None:
        entries: dict[str, SkillEntry] = {}
        if not self._root_dir.exists():
            self._entries = entries
            return

        for path in sorted(self._root_dir.rglob("SKILL.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue

            key = _derive_skill_key(self._root_dir, path)
            fm, body = parse_skill_frontmatter(text)

            # Name: frontmatter > heading > directory name
            name = (fm.name if fm else "") or _extract_heading(body) or path.parent.name
            description = (fm.description if fm else "") or _extract_description(body)
            homepage = (fm.homepage if fm else "")

            # Metadata from the ``openclaw`` JSON key
            meta = fm.metadata if fm else None
            emoji = meta.emoji if meta else ""
            primary_env = meta.primary_env if meta else ""
            required_bins = list(meta.required_bins) if meta else []
            # anyBins also counts as required bins for display purposes
            if meta and meta.required_any_bins and not required_bins:
                required_bins = list(meta.required_any_bins)
            required_env = list(meta.required_env) if meta else []
            required_config = list(meta.required_config) if meta else []
            required_os = list(meta.os) if meta else []

            install_options: list[SkillInstallOption] = []
            if meta and meta.install:
                for spec in meta.install:
                    install_options.append(
                        SkillInstallOption(
                            id=spec.id or spec.kind,
                            kind=spec.kind,
                            label=spec.label,
                            bins=list(spec.bins),
                        )
                    )

            if homepage and not homepage.strip():
                homepage = meta.homepage if meta else ""

            entries[key] = SkillEntry(
                key=key,
                name=name,
                description=description,
                file_path=str(path),
                emoji=emoji,
                homepage=homepage,
                primary_env=primary_env,
                source="openclaw-bundled",
                bundled=True,
                required_bins=required_bins,
                required_env=required_env,
                required_config=required_config,
                required_os=required_os,
                install=install_options,
            )
        self._entries = entries

    def list(self, skill_filter: tuple[str, ...] | None = None) -> list[SkillEntry]:
        """Return skill entries filtered by *skill_filter*.

        Semantics (aligned with openclaw):
        - ``None``      → no filter, return ALL skills
        - ``()``        → explicit disable, return empty
        - non-empty     → return only matching skills
        """
        values = list(self._entries.values())
        if skill_filter is None:
            return sorted(values, key=lambda e: e.key)
        accepted = {item.strip() for item in skill_filter if item.strip()}
        if not accepted:
            return []
        return sorted(
            [e for e in values if e.key in accepted or e.name in accepted],
            key=lambda e: e.key,
        )


# ---------------------------------------------------------------------------
# Status helpers — used by the gateway WebSocket API
# ---------------------------------------------------------------------------


def compute_missing_bins(required_bins: list[str]) -> list[str]:
    """Return required binaries that are not on ``PATH``."""
    return [b for b in required_bins if not shutil.which(b)]


def compute_missing_env(required_env: list[str]) -> list[str]:
    """Return required env vars that are empty / unset."""
    return [e for e in required_env if not os.environ.get(e)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _derive_skill_key(root_dir: Path, skill_file: Path) -> str:
    try:
        rel = skill_file.relative_to(root_dir)
        parts = rel.parts
        if len(parts) >= 2:
            return parts[-2]
    except Exception:
        pass
    return skill_file.parent.name


def _extract_heading(body: str) -> str:
    for line in body.splitlines():
        m = _SKILL_HEADING.match(line.strip())
        if m:
            return m.group(1).strip()
    return ""


def _extract_description(body: str) -> str:
    for line in body.splitlines():
        m = _SKILL_DESC.match(line.strip())
        if m:
            return m.group(1).strip()
    return ""

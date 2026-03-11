from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_SKILL_HEADING = re.compile(r"^#\s+(.+)$")
_SKILL_DESC = re.compile(r"^>\s*(.+)$")


@dataclass(frozen=True)
class SkillEntry:
    key: str
    name: str
    description: str
    file_path: str


class SkillCatalog:
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
            name, description = _extract_title_and_description(path, text)
            key = _derive_skill_key(self._root_dir, path)
            entries[key] = SkillEntry(
                key=key,
                name=name,
                description=description,
                file_path=str(path),
            )
        self._entries = entries

    def list(self, skill_filter: tuple[str, ...] | None = None) -> list[SkillEntry]:
        values = list(self._entries.values())
        if skill_filter is None:
            return sorted(values, key=lambda item: item.key)
        accepted = {item.strip() for item in skill_filter if item.strip()}
        if not accepted:
            return []
        return sorted(
            [item for item in values if item.key in accepted or item.name in accepted],
            key=lambda item: item.key,
        )


def _derive_skill_key(root_dir: Path, skill_file: Path) -> str:
    try:
        rel = skill_file.relative_to(root_dir)
        parts = rel.parts
        if len(parts) >= 2:
            return parts[-2]
    except Exception:
        pass
    return skill_file.parent.name


def _extract_title_and_description(skill_path: Path, text: str) -> tuple[str, str]:
    name = skill_path.parent.name
    description = ""
    for line in text.splitlines():
        if not name:
            heading = _SKILL_HEADING.match(line.strip())
            if heading:
                name = heading.group(1).strip()
        if not description:
            desc = _SKILL_DESC.match(line.strip())
            if desc:
                description = desc.group(1).strip()
        if name and description:
            break
    return name, description

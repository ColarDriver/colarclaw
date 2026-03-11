"""Model alias lines — ported from bk/src/agents/model-alias-lines.ts."""
from __future__ import annotations
import re
from typing import Any

ALIAS_LINE_RE = re.compile(r"^([a-zA-Z0-9_-]+)\s*=\s*(.+)$")

def parse_model_alias_line(line: str) -> tuple[str, str] | None:
    m = ALIAS_LINE_RE.match(line.strip())
    if not m:
        return None
    alias = m.group(1).strip().lower()
    target = m.group(2).strip()
    return (alias, target) if alias and target else None

def parse_model_alias_lines(text: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for line in text.splitlines():
        result = parse_model_alias_line(line)
        if result:
            aliases[result[0]] = result[1]
    return aliases

def resolve_model_alias(model: str, aliases: dict[str, str]) -> str:
    lower = model.strip().lower()
    return aliases.get(lower, model)

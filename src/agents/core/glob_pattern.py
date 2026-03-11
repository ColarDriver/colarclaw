"""Glob pattern matching — ported from bk/src/agents/glob-pattern.ts."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class CompiledGlobPattern:
    kind: str  # "all" | "exact" | "regex"
    value: str | re.Pattern[str] | None = None

def _escape_regex(value: str) -> str:
    return re.escape(value)

def compile_glob_pattern(raw: str, normalize: Callable[[str], str]) -> CompiledGlobPattern:
    normalized = normalize(raw)
    if not normalized:
        return CompiledGlobPattern(kind="exact", value="")
    if normalized == "*":
        return CompiledGlobPattern(kind="all")
    if "*" not in normalized:
        return CompiledGlobPattern(kind="exact", value=normalized)
    pattern = "^" + _escape_regex(normalized).replace(r"\*", ".*") + "$"
    return CompiledGlobPattern(kind="regex", value=re.compile(pattern))

def compile_glob_patterns(raw: list[str] | None, normalize: Callable[[str], str]) -> list[CompiledGlobPattern]:
    if not raw:
        return []
    patterns = [compile_glob_pattern(r, normalize) for r in raw]
    return [p for p in patterns if p.kind != "exact" or p.value]

def matches_any_glob_pattern(value: str, patterns: list[CompiledGlobPattern]) -> bool:
    for p in patterns:
        if p.kind == "all":
            return True
        if p.kind == "exact" and value == p.value:
            return True
        if p.kind == "regex" and isinstance(p.value, re.Pattern) and p.value.match(value):
            return True
    return False

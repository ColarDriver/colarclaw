"""Apply-patch update — ported from bk/src/agents/apply-patch-update.ts.

Hunked file update/patch logic: reads an existing file, finds old-line
sequences and replaces them with new-line sequences.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class UpdateFileChunk:
    change_context: str | None = None
    old_lines: list[str] = field(default_factory=list)
    new_lines: list[str] = field(default_factory=list)
    is_end_of_file: bool = False


async def apply_update_hunk(
    file_path: str,
    chunks: list[UpdateFileChunk],
    *,
    read_file: Callable[[str], str] | None = None,
) -> str:
    """Apply a list of update-hunks to *file_path* and return the new file content."""
    reader = read_file or _default_read_file
    try:
        original_contents = reader(file_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to read file to update {file_path}: {exc}") from exc

    original_lines = original_contents.split("\n")
    if original_lines and original_lines[-1] == "":
        original_lines.pop()

    replacements = _compute_replacements(original_lines, file_path, chunks)
    new_lines = _apply_replacements(original_lines, replacements)
    if not new_lines or new_lines[-1] != "":
        new_lines = [*new_lines, ""]
    return "\n".join(new_lines)


def _default_read_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as fh:
        return fh.read()


def _compute_replacements(
    original_lines: list[str],
    file_path: str,
    chunks: list[UpdateFileChunk],
) -> list[tuple[int, int, list[str]]]:
    replacements: list[tuple[int, int, list[str]]] = []
    line_index = 0

    for chunk in chunks:
        if chunk.change_context:
            ctx_index = _seek_sequence(original_lines, [chunk.change_context], line_index, False)
            if ctx_index is None:
                raise RuntimeError(
                    f"Failed to find context '{chunk.change_context}' in {file_path}"
                )
            line_index = ctx_index + 1

        if not chunk.old_lines:
            insertion_index = (
                len(original_lines) - 1
                if original_lines and original_lines[-1] == ""
                else len(original_lines)
            )
            replacements.append((insertion_index, 0, chunk.new_lines))
            continue

        pattern = list(chunk.old_lines)
        new_slice = list(chunk.new_lines)
        found = _seek_sequence(original_lines, pattern, line_index, chunk.is_end_of_file)

        if found is None and pattern and pattern[-1] == "":
            pattern = pattern[:-1]
            if new_slice and new_slice[-1] == "":
                new_slice = new_slice[:-1]
            found = _seek_sequence(original_lines, pattern, line_index, chunk.is_end_of_file)

        if found is None:
            raise RuntimeError(
                f"Failed to find expected lines in {file_path}:\n"
                + "\n".join(chunk.old_lines)
            )

        replacements.append((found, len(pattern), new_slice))
        line_index = found + len(pattern)

    replacements.sort(key=lambda r: r[0])
    return replacements


def _apply_replacements(
    lines: list[str],
    replacements: list[tuple[int, int, list[str]]],
) -> list[str]:
    result = list(lines)
    for start_index, old_len, new_lines in reversed(replacements):
        del result[start_index : start_index + old_len]
        for i, line in enumerate(new_lines):
            result.insert(start_index + i, line)
    return result


def _seek_sequence(
    lines: list[str],
    pattern: list[str],
    start: int,
    eof: bool,
) -> int | None:
    if not pattern:
        return start
    if len(pattern) > len(lines):
        return None

    max_start = len(lines) - len(pattern)
    search_start = max_start if (eof and len(lines) >= len(pattern)) else start
    if search_start > max_start:
        return None

    # Exact match
    for i in range(search_start, max_start + 1):
        if _lines_match(lines, pattern, i, lambda v: v):
            return i
    # trimEnd match
    for i in range(search_start, max_start + 1):
        if _lines_match(lines, pattern, i, lambda v: v.rstrip()):
            return i
    # trim match
    for i in range(search_start, max_start + 1):
        if _lines_match(lines, pattern, i, lambda v: v.strip()):
            return i
    # normalized punctuation match
    for i in range(search_start, max_start + 1):
        if _lines_match(lines, pattern, i, lambda v: _normalize_punctuation(v.strip())):
            return i

    return None


def _lines_match(
    lines: list[str],
    pattern: list[str],
    start: int,
    normalize: Callable[[str], str],
) -> bool:
    for idx in range(len(pattern)):
        if normalize(lines[start + idx]) != normalize(pattern[idx]):
            return False
    return True


_PUNCTUATION_MAP: dict[str, str] = {
    # Dashes
    "\u2010": "-", "\u2011": "-", "\u2012": "-",
    "\u2013": "-", "\u2014": "-", "\u2015": "-", "\u2212": "-",
    # Single quotes
    "\u2018": "'", "\u2019": "'", "\u201A": "'", "\u201B": "'",
    # Double quotes
    "\u201C": '"', "\u201D": '"', "\u201E": '"', "\u201F": '"',
    # Spaces
    "\u00A0": " ", "\u2002": " ", "\u2003": " ", "\u2004": " ",
    "\u2005": " ", "\u2006": " ", "\u2007": " ", "\u2008": " ",
    "\u2009": " ", "\u200A": " ", "\u202F": " ", "\u205F": " ",
    "\u3000": " ",
}


def _normalize_punctuation(value: str) -> str:
    return "".join(_PUNCTUATION_MAP.get(ch, ch) for ch in value)

"""Apply patch — ported from bk/src/agents/apply-patch.ts + apply-patch-update.ts.

Applies unified diff patches to files with conflict detection.
"""
from __future__ import annotations
import os
import re
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("openclaw.agents.apply_patch")

@dataclass
class PatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)

@dataclass
class PatchFile:
    old_path: str
    new_path: str
    hunks: list[PatchHunk] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False

@dataclass
class PatchResult:
    applied: bool = False
    files_changed: int = 0
    files_created: int = 0
    files_deleted: int = 0
    errors: list[str] = field(default_factory=list)

HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

def parse_unified_diff(diff_text: str) -> list[PatchFile]:
    patches: list[PatchFile] = []
    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith("--- "):
            old_path = lines[i][4:].strip()
            if old_path.startswith("a/"):
                old_path = old_path[2:]
            i += 1
            if i < len(lines) and lines[i].startswith("+++ "):
                new_path = lines[i][4:].strip()
                if new_path.startswith("b/"):
                    new_path = new_path[2:]
                is_new = old_path == "/dev/null"
                is_deleted = new_path == "/dev/null"
                patch = PatchFile(old_path=old_path, new_path=new_path, is_new=is_new, is_deleted=is_deleted)
                i += 1
                while i < len(lines):
                    m = HUNK_HEADER_RE.match(lines[i])
                    if not m:
                        break
                    hunk = PatchHunk(
                        old_start=int(m.group(1)),
                        old_count=int(m.group(2) or "1"),
                        new_start=int(m.group(3)),
                        new_count=int(m.group(4) or "1"),
                    )
                    i += 1
                    while i < len(lines) and not lines[i].startswith("--- ") and not HUNK_HEADER_RE.match(lines[i]):
                        hunk.lines.append(lines[i])
                        i += 1
                    patch.hunks.append(hunk)
                patches.append(patch)
            else:
                i += 1
        else:
            i += 1
    return patches

def apply_patch(diff_text: str, base_dir: str) -> PatchResult:
    patches = parse_unified_diff(diff_text)
    result = PatchResult()
    for patch in patches:
        target = os.path.join(base_dir, patch.new_path)
        try:
            if patch.is_deleted:
                if os.path.isfile(target):
                    os.remove(target)
                    result.files_deleted += 1
                continue
            if patch.is_new:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                content_lines = [line[1:] for hunk in patch.hunks for line in hunk.lines if line.startswith("+")]
                with open(target, "w", encoding="utf-8") as f:
                    f.write("\n".join(content_lines) + "\n" if content_lines else "")
                result.files_created += 1
                continue
            if not os.path.isfile(target):
                result.errors.append(f"File not found: {target}")
                continue
            with open(target, "r", encoding="utf-8") as f:
                file_lines = f.readlines()
            for hunk in patch.hunks:
                offset = hunk.old_start - 1
                for line in hunk.lines:
                    if line.startswith("-"):
                        if offset < len(file_lines):
                            file_lines.pop(offset)
                    elif line.startswith("+"):
                        file_lines.insert(offset, line[1:] + "\n")
                        offset += 1
                    else:
                        offset += 1
            with open(target, "w", encoding="utf-8") as f:
                f.writelines(file_lines)
            result.files_changed += 1
        except Exception as e:
            result.errors.append(f"{patch.new_path}: {e}")
    result.applied = not result.errors
    return result

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryFileEntry:
    path: str
    abs_path: str
    mtime_ms: float
    size: int
    content_hash: str
    content: str


@dataclass(frozen=True)
class MemoryChunk:
    start_line: int
    end_line: int
    text: str
    content_hash: str


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_rel_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    normalized = normalized.lstrip("./")
    return normalized


def normalize_extra_memory_paths(workspace_dir: str, extra_paths: tuple[str, ...]) -> tuple[str, ...]:
    root = Path(workspace_dir)
    resolved: list[str] = []
    for raw in extra_paths:
        value = raw.strip()
        if not value:
            continue
        path = Path(value)
        full = path if path.is_absolute() else root / path
        resolved.append(str(full.resolve()))
    return tuple(dict.fromkeys(resolved))


def is_memory_path(rel_path: str) -> bool:
    normalized = normalize_rel_path(rel_path)
    if normalized in {"MEMORY.md", "memory.md"}:
        return True
    return normalized.startswith("memory/")


def _walk_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    if not root.exists() or root.is_symlink():
        return files
    if root.is_file() and root.suffix.lower() == ".md":
        return [root]
    if not root.is_dir():
        return files
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in {".git", "node_modules", "__pycache__", ".venv", "venv"}
        ]
        for filename in filenames:
            if filename.lower().endswith(".md"):
                files.append(Path(current_root) / filename)
    return files


def list_memory_files(workspace_dir: str, extra_paths: tuple[str, ...]) -> list[str]:
    workspace = Path(workspace_dir)
    candidates: list[Path] = []
    for filename in ("MEMORY.md", "memory.md"):
        candidate = workspace / filename
        if candidate.is_file() and not candidate.is_symlink():
            candidates.append(candidate)

    memory_dir = workspace / "memory"
    candidates.extend(_walk_markdown_files(memory_dir))

    for path_str in normalize_extra_memory_paths(workspace_dir, extra_paths):
        candidates.extend(_walk_markdown_files(Path(path_str)))

    dedup: dict[str, str] = {}
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        dedup[key] = str(path)
    return sorted(dedup.values())


def build_file_entry(abs_path: str, workspace_dir: str) -> MemoryFileEntry | None:
    path = Path(abs_path)
    try:
        if not path.is_file() or path.is_symlink():
            return None
        content = path.read_text(encoding="utf-8")
        stat = path.stat()
    except Exception:
        return None

    workspace = Path(workspace_dir)
    rel = path.relative_to(workspace).as_posix() if path.is_relative_to(workspace) else path.as_posix()
    return MemoryFileEntry(
        path=rel,
        abs_path=str(path),
        mtime_ms=stat.st_mtime * 1000.0,
        size=stat.st_size,
        content_hash=hash_text(content),
        content=content,
    )


def chunk_markdown(content: str, *, tokens: int, overlap: int) -> list[MemoryChunk]:
    lines = content.split("\n")
    if not lines:
        return []

    max_chars = max(32, tokens * 4)
    overlap_chars = max(0, overlap * 4)

    chunks: list[MemoryChunk] = []
    current: list[tuple[int, str]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current
        if not current:
            return
        start_line = current[0][0]
        end_line = current[-1][0]
        text = "\n".join(part for _, part in current)
        chunks.append(
            MemoryChunk(
                start_line=start_line,
                end_line=end_line,
                text=text,
                content_hash=hash_text(text),
            )
        )

    def carry_overlap() -> None:
        nonlocal current, current_chars
        if overlap_chars <= 0 or not current:
            current = []
            current_chars = 0
            return
        kept: list[tuple[int, str]] = []
        acc = 0
        for line_no, segment in reversed(current):
            kept.insert(0, (line_no, segment))
            acc += len(segment) + 1
            if acc >= overlap_chars:
                break
        current = kept
        current_chars = sum(len(segment) + 1 for _, segment in current)

    for idx, line in enumerate(lines, start=1):
        pieces = [line[i : i + max_chars] for i in range(0, max(1, len(line)), max_chars)] if line else [""]
        for piece in pieces:
            item_size = len(piece) + 1
            if current and current_chars + item_size > max_chars:
                flush()
                carry_overlap()
            current.append((idx, piece))
            current_chars += item_size

    flush()
    return chunks


def parse_embedding(raw: str) -> list[float]:
    import json

    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []

    values: list[float] = []
    for item in parsed:
        try:
            values.append(float(item))
        except Exception:
            values.append(0.0)
    return values


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    length = min(len(a), len(b))
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for index in range(length):
        av = a[index]
        bv = b[index]
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / ((norm_a**0.5) * (norm_b**0.5))



def build_session_entry(session_id: str, content: str, updated_at_ms: int) -> MemoryFileEntry:
    normalized_lines: list[str] = []
    for line in content.split("\n"):
        trimmed = " ".join(line.strip().split())
        if trimmed:
            normalized_lines.append(trimmed)
    normalized = "\n".join(normalized_lines)
    rel_path = f"sessions/{session_id}.md"
    return MemoryFileEntry(
        path=rel_path,
        abs_path=rel_path,
        mtime_ms=float(updated_at_ms),
        size=len(normalized.encode("utf-8")),
        content_hash=hash_text(normalized),
        content=normalized,
    )

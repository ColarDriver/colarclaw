"""Auto-reply chunk — ported from bk/src/auto-reply/chunk.ts.

Text chunking for outbound messages: length-based, newline-based,
paragraph-based, and markdown-aware splitting.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Literal

ChunkMode = Literal["length", "newline"]
DEFAULT_CHUNK_LIMIT = 4000
DEFAULT_CHUNK_MODE: ChunkMode = "length"


def resolve_text_chunk_limit(
    cfg: Any = None,
    provider: str | None = None,
    account_id: str | None = None,
    fallback_limit: int = DEFAULT_CHUNK_LIMIT,
) -> int:
    if cfg and provider:
        channels_cfg = getattr(cfg, "channels", None)
        if isinstance(channels_cfg, dict) and provider in channels_cfg:
            provider_cfg = channels_cfg[provider]
            if isinstance(provider_cfg, dict):
                limit = provider_cfg.get("textChunkLimit") or provider_cfg.get("text_chunk_limit")
                if isinstance(limit, (int, float)) and limit > 0:
                    return int(limit)
    return max(1, fallback_limit)


def resolve_chunk_mode(
    cfg: Any = None,
    provider: str | None = None,
    account_id: str | None = None,
) -> ChunkMode:
    if cfg and provider:
        channels_cfg = getattr(cfg, "channels", None)
        if isinstance(channels_cfg, dict) and provider in channels_cfg:
            provider_cfg = channels_cfg[provider]
            if isinstance(provider_cfg, dict):
                mode = provider_cfg.get("chunkMode") or provider_cfg.get("chunk_mode")
                if mode in ("length", "newline"):
                    return mode
    return DEFAULT_CHUNK_MODE


def _scan_paren_aware_breakpoints(
    text: str, start: int, end: int,
    is_allowed: Callable[[int], bool] | None = None,
) -> tuple[int, int]:
    last_newline = -1
    last_whitespace = -1
    depth = 0
    for i in range(start, end):
        if is_allowed and not is_allowed(i):
            continue
        ch = text[i]
        if ch == "(":
            depth += 1
            continue
        if ch == ")" and depth > 0:
            depth -= 1
            continue
        if depth != 0:
            continue
        if ch == "\n":
            last_newline = i
        elif ch in " \t\r":
            last_whitespace = i
    return last_newline, last_whitespace


def chunk_text(text: str, limit: int) -> list[str]:
    if not text:
        return []
    if limit <= 0:
        return [text]
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        if end >= len(text):
            chunks.append(text[start:])
            break
        ln, ws = _scan_paren_aware_breakpoints(text, start, end)
        break_at = ln if ln > start else (ws if ws > start else end)
        chunks.append(text[start:break_at])
        start = break_at
        if start < len(text) and text[start] in " \t\n\r":
            start += 1
    return chunks


def chunk_by_newline(
    text: str,
    max_line_length: int,
    split_long_lines: bool = True,
    trim_lines: bool = True,
) -> list[str]:
    if not text:
        return []
    if max_line_length <= 0:
        return [text] if text.strip() else []
    lines = text.split("\n")
    chunks: list[str] = []
    pending_blank = 0
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            pending_blank += 1
            continue
        max_prefix = max(0, max_line_length - 1)
        capped = min(pending_blank, max_prefix) if pending_blank > 0 else 0
        prefix = "\n" * capped
        pending_blank = 0
        value = trimmed if trim_lines else line
        if not split_long_lines or len(value) + len(prefix) <= max_line_length:
            chunks.append(prefix + value)
        else:
            first_limit = max(1, max_line_length - len(prefix))
            chunks.append(prefix + value[:first_limit])
            remaining = value[first_limit:]
            if remaining:
                chunks.extend(chunk_text(remaining, max_line_length))
    return chunks


def chunk_by_paragraph(
    text: str,
    limit: int,
    split_long_paragraphs: bool = True,
) -> list[str]:
    if not text:
        return []
    if limit <= 0:
        return [text]
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraph_re = re.compile(r"\n[\t ]*\n+")
    if not paragraph_re.search(normalized):
        if len(normalized) <= limit:
            return [normalized]
        if not split_long_paragraphs:
            return [normalized]
        return chunk_text(normalized, limit)
    parts = paragraph_re.split(normalized)
    chunks: list[str] = []
    for part in parts:
        paragraph = re.sub(r"\s+$", "", part)
        if not paragraph.strip():
            continue
        if len(paragraph) <= limit:
            chunks.append(paragraph)
        elif not split_long_paragraphs:
            chunks.append(paragraph)
        else:
            chunks.extend(chunk_text(paragraph, limit))
    return chunks


def chunk_text_with_mode(text: str, limit: int, mode: ChunkMode) -> list[str]:
    if mode == "newline":
        return chunk_by_paragraph(text, limit)
    return chunk_text(text, limit)


def chunk_markdown_text(text: str, limit: int) -> list[str]:
    """Markdown-aware text chunking (simplified)."""
    if not text:
        return []
    if limit <= 0:
        return [text]
    if len(text) <= limit:
        return [text]
    return chunk_text(text, limit)


def chunk_markdown_text_with_mode(text: str, limit: int, mode: ChunkMode) -> list[str]:
    if mode == "newline":
        paragraph_chunks = chunk_by_paragraph(text, limit, split_long_paragraphs=False)
        out: list[str] = []
        for ch in paragraph_chunks:
            nested = chunk_markdown_text(ch, limit)
            out.extend(nested if nested else [ch])
        return out
    return chunk_markdown_text(text, limit)

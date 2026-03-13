"""Shared text processing — ported from bk/src/shared/text/reasoning-tags.ts,
text/assistant-visible-text.ts, text/join-segments.ts, text/code-regions.ts,
subagents-format.ts, text-chunking.ts.

Reasoning tag stripping, text formatting, token display, code region detection.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


# ─── code-regions.ts ───

@dataclass
class CodeRegion:
    start: int
    end: int
    kind: str  # "fenced" | "inline"


def find_code_regions(text: str) -> list[CodeRegion]:
    """Find fenced and inline code regions in text."""
    regions: list[CodeRegion] = []

    # Fenced code blocks: ```...```
    for m in re.finditer(r"```[^\n]*\n.*?```", text, re.DOTALL):
        regions.append(CodeRegion(start=m.start(), end=m.end(), kind="fenced"))

    # Inline code: `...`
    for m in re.finditer(r"`[^`\n]+`", text):
        # Don't include if inside a fenced block
        if not any(r.start <= m.start() and m.end() <= r.end for r in regions):
            regions.append(CodeRegion(start=m.start(), end=m.end(), kind="inline"))

    return sorted(regions, key=lambda r: r.start)


def is_inside_code(pos: int, regions: list[CodeRegion]) -> bool:
    """Check if a position is inside a code region."""
    return any(r.start <= pos < r.end for r in regions)


# ─── reasoning-tags.ts ───

_QUICK_TAG_RE = re.compile(r"<\s*/?\s*(?:think(?:ing)?|thought|antthinking|final)\b", re.IGNORECASE)
_FINAL_TAG_RE = re.compile(r"<\s*/?\s*final\b[^<>]*>", re.IGNORECASE)
_THINKING_TAG_RE = re.compile(
    r"<\s*(/?)?\s*(?:think(?:ing)?|thought|antthinking)\b[^<>]*>",
    re.IGNORECASE,
)


def strip_reasoning_tags_from_text(
    text: str,
    mode: str = "strict",  # "strict" | "preserve"
    trim: str = "both",    # "none" | "start" | "both"
) -> str:
    """Strip reasoning tags from text, preserving code blocks."""
    if not text:
        return text
    if not _QUICK_TAG_RE.search(text):
        return text

    cleaned = text

    # Remove <final> tags (but not inside code)
    if _FINAL_TAG_RE.search(cleaned):
        regions = find_code_regions(cleaned)
        matches = list(_FINAL_TAG_RE.finditer(cleaned))
        for m in reversed(matches):
            if not is_inside_code(m.start(), regions):
                cleaned = cleaned[:m.start()] + cleaned[m.end():]

    # Remove <think*>...</think*> blocks
    if mode == "strict":
        regions = find_code_regions(cleaned)
        # Remove opening/closing thinking tags that aren't inside code
        result = []
        last_end = 0
        inside_block = False
        for m in _THINKING_TAG_RE.finditer(cleaned):
            if is_inside_code(m.start(), regions):
                continue
            is_closing = bool(m.group(1))
            if not is_closing:
                # Opening tag — start stripping
                result.append(cleaned[last_end:m.start()])
                inside_block = True
                last_end = m.end()
            elif inside_block:
                # Closing tag — stop stripping
                inside_block = False
                last_end = m.end()
            else:
                # Orphan closing tag — just remove it
                result.append(cleaned[last_end:m.start()])
                last_end = m.end()
        result.append(cleaned[last_end:])
        cleaned = "".join(result)

    # Apply trim
    if trim == "start":
        cleaned = cleaned.lstrip()
    elif trim == "both":
        cleaned = cleaned.strip()

    return cleaned


# ─── assistant-visible-text.ts ───

def extract_assistant_visible_text(text: str) -> str:
    """Extract the visible portion of assistant text (strip reasoning)."""
    return strip_reasoning_tags_from_text(text).strip()


# ─── join-segments.ts ───

def join_text_segments(
    segments: list[str],
    separator: str = "\n\n",
    strip_each: bool = True,
) -> str:
    """Join text segments with separator, filtering empty ones."""
    parts = [s.strip() if strip_each else s for s in segments]
    return separator.join(p for p in parts if p)


# ─── subagents-format.ts ───

def format_duration_compact(value_ms: float | int | None) -> str:
    """Format milliseconds to compact duration string."""
    if not value_ms or not math.isfinite(value_ms) or value_ms <= 0:
        return "n/a"
    minutes = max(1, round(value_ms / 60_000))
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    minutes_rem = minutes % 60
    if hours < 24:
        return f"{hours}h{minutes_rem}m" if minutes_rem > 0 else f"{hours}h"
    days = hours // 24
    hours_rem = hours % 24
    return f"{days}d{hours_rem}h" if hours_rem > 0 else f"{days}d"


def format_token_short(value: float | int | None) -> str | None:
    """Format token count in short form (1k, 2.5m, etc.)."""
    if not value or not math.isfinite(value) or value <= 0:
        return None
    n = int(value)
    if n < 1_000:
        return str(n)
    if n < 10_000:
        v = n / 1_000
        s = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{s}k"
    if n < 1_000_000:
        return f"{round(n / 1_000)}k"
    v = n / 1_000_000
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{s}m"


def truncate_line(value: str, max_length: int) -> str:
    """Truncate a line with ellipsis."""
    if len(value) <= max_length:
        return value
    return value[:max_length].rstrip() + "..."


def resolve_total_tokens(entry: dict[str, Any] | None) -> int | None:
    """Resolve total tokens from a usage entry."""
    if not entry or not isinstance(entry, dict):
        return None
    total = entry.get("totalTokens")
    if isinstance(total, (int, float)) and math.isfinite(total):
        return int(total)
    inp = entry.get("inputTokens", 0)
    out = entry.get("outputTokens", 0)
    inp = inp if isinstance(inp, (int, float)) else 0
    out = out if isinstance(out, (int, float)) else 0
    total_val = int(inp) + int(out)
    return total_val if total_val > 0 else None


def resolve_io_tokens(entry: dict[str, Any] | None) -> dict[str, int] | None:
    """Resolve input/output/total tokens."""
    if not entry or not isinstance(entry, dict):
        return None
    inp = entry.get("inputTokens", 0)
    out = entry.get("outputTokens", 0)
    inp = int(inp) if isinstance(inp, (int, float)) and math.isfinite(inp) else 0
    out = int(out) if isinstance(out, (int, float)) and math.isfinite(out) else 0
    total = inp + out
    if total <= 0:
        return None
    return {"input": inp, "output": out, "total": total}


def format_token_usage_display(entry: dict[str, Any] | None) -> str:
    """Format token usage for display."""
    io = resolve_io_tokens(entry)
    prompt_cache = resolve_total_tokens(entry)
    parts: list[str] = []
    if io:
        inp = format_token_short(io["input"]) or "0"
        out = format_token_short(io["output"]) or "0"
        parts.append(f"tokens {format_token_short(io['total'])} (in {inp} / out {out})")
    elif isinstance(prompt_cache, int) and prompt_cache > 0:
        parts.append(f"tokens {format_token_short(prompt_cache)} prompt/cache")
    if isinstance(prompt_cache, int) and io and prompt_cache > io["total"]:
        parts.append(f"prompt/cache {format_token_short(prompt_cache)}")
    return ", ".join(parts)


# ─── text-chunking.ts ───

def chunk_text_by_limit(
    text: str,
    max_length: int,
    separator: str = "\n",
) -> list[str]:
    """Split text into chunks at separator boundaries."""
    if len(text) <= max_length:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break
        split = remaining.rfind(separator, 0, max_length)
        if split <= 0:
            split = max_length
        chunks.append(remaining[:split])
        remaining = remaining[split:].lstrip(separator)
    return chunks

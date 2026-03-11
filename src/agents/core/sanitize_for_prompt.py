"""Sanitize for prompt — ported from bk/src/agents/sanitize-for-prompt.ts.

Sanitizes user input for safe inclusion in LLM prompts.
"""
from __future__ import annotations
import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EXCESSIVE_NEWLINES = re.compile(r"\n{4,}")

def sanitize_for_prompt(text: str, max_length: int | None = None) -> str:
    if not text:
        return ""
    sanitized = _CONTROL_CHARS.sub("", text)
    sanitized = _EXCESSIVE_NEWLINES.sub("\n\n\n", sanitized)
    sanitized = sanitized.strip()
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "…"
    return sanitized

def truncate_for_display(text: str, max_length: int = 200) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

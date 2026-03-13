"""Shared string normalization — ported from bk/src/shared/string-normalization.ts.

Slug normalization and string list utilities.
"""
from __future__ import annotations

import re


def normalize_string_entries(lst: list | None = None) -> list[str]:
    """Normalize a list of values to trimmed non-empty strings."""
    return [s for v in (lst or []) if (s := str(v).strip())]


def normalize_string_entries_lower(lst: list | None = None) -> list[str]:
    """Normalize entries to lowercase."""
    return [s.lower() for s in normalize_string_entries(lst)]


def normalize_hyphen_slug(raw: str | None) -> str:
    """Normalize a slug: lowercase, dashes, allowed chars [a-z0-9#@._+-]."""
    trimmed = (raw or "").strip().lower()
    if not trimmed:
        return ""
    dashed = re.sub(r"\s+", "-", trimmed)
    cleaned = re.sub(r"[^a-z0-9#@._+\-]+", "-", dashed)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-.")


def normalize_at_hash_slug(raw: str | None) -> str:
    """Normalize a slug, stripping leading @/# prefixes."""
    trimmed = (raw or "").strip().lower()
    if not trimmed:
        return ""
    without_prefix = re.sub(r"^[@#]+", "", trimmed)
    dashed = re.sub(r"[\s_]+", "-", without_prefix)
    cleaned = re.sub(r"[^a-z0-9\-]+", "-", dashed)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-")


def string_sample(value: str, max_len: int = 80) -> str:
    """Return a truncated sample of a string."""
    if len(value) <= max_len:
        return value
    return value[:max_len - 3].rstrip() + "..."

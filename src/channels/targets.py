"""Channels targets — ported from bk/src/channels/targets.ts.

Messaging target parsing, normalization, and construction utilities.
Supports mention patterns, prefix-based parsing, and @user targets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


# ─── types ───

MessagingTargetKind = Literal["user", "channel"]


@dataclass
class MessagingTarget:
    kind: MessagingTargetKind
    id: str
    raw: str
    normalized: str


@dataclass
class MessagingTargetParseOptions:
    default_kind: MessagingTargetKind = "user"
    ambiguous_message: str = ""


# ─── functions ───

def normalize_target_id(kind: MessagingTargetKind, target_id: str) -> str:
    """Create normalized target identifier."""
    return f"{kind}:{target_id}".lower()


def build_messaging_target(kind: MessagingTargetKind, target_id: str, raw: str) -> MessagingTarget:
    """Build a MessagingTarget with normalized ID."""
    return MessagingTarget(
        kind=kind,
        id=target_id,
        raw=raw,
        normalized=normalize_target_id(kind, target_id),
    )


def ensure_target_id(candidate: str, pattern: re.Pattern[str], error_message: str) -> str:
    """Validate a target ID matches the expected pattern."""
    if not pattern.search(candidate):
        raise ValueError(error_message)
    return candidate


def parse_target_mention(
    raw: str,
    mention_pattern: re.Pattern[str],
    kind: MessagingTargetKind,
) -> MessagingTarget | None:
    """Parse a target from a mention pattern (e.g., <@123456>)."""
    match = mention_pattern.search(raw)
    if not match or not match.group(1):
        return None
    return build_messaging_target(kind, match.group(1), raw)


def parse_target_prefix(
    raw: str,
    prefix: str,
    kind: MessagingTargetKind,
) -> MessagingTarget | None:
    """Parse a target from a prefix (e.g., user:123 or channel:#general)."""
    if not raw.startswith(prefix):
        return None
    target_id = raw[len(prefix):].strip()
    return build_messaging_target(kind, target_id, raw) if target_id else None


def parse_target_prefixes(
    raw: str,
    prefixes: list[tuple[str, MessagingTargetKind]],
) -> MessagingTarget | None:
    """Try multiple prefix+kind pairs in order."""
    for prefix, kind in prefixes:
        result = parse_target_prefix(raw, prefix, kind)
        if result:
            return result
    return None


def parse_at_user_target(
    raw: str,
    pattern: re.Pattern[str],
    error_message: str,
) -> MessagingTarget | None:
    """Parse @username targets."""
    if not raw.startswith("@"):
        return None
    candidate = raw[1:].strip()
    target_id = ensure_target_id(candidate, pattern, error_message)
    return build_messaging_target("user", target_id, raw)


def parse_mention_prefix_or_at_user_target(
    raw: str,
    mention_pattern: re.Pattern[str],
    prefixes: list[tuple[str, MessagingTargetKind]],
    at_user_pattern: re.Pattern[str],
    at_user_error_message: str,
) -> MessagingTarget | None:
    """Try mention pattern → prefixes → @user target, in order."""
    result = parse_target_mention(raw, mention_pattern, "user")
    if result:
        return result
    result = parse_target_prefixes(raw, prefixes)
    if result:
        return result
    return parse_at_user_target(raw, at_user_pattern, at_user_error_message)


def require_target_kind(
    platform: str,
    target: MessagingTarget | None,
    kind: MessagingTargetKind,
) -> str:
    """Require a target of a specific kind, raising ValueError if not found."""
    if not target:
        raise ValueError(f"{platform} {kind} id is required.")
    if target.kind != kind:
        raise ValueError(f"{platform} {kind} id is required (use {kind}:<id>).")
    return target.id

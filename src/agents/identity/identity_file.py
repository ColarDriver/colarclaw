"""Identity file parser — ported from bk/src/agents/identity-file.ts.

Parses IDENTITY.md files to extract agent identity fields.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass
class AgentIdentityFile:
    name: str | None = None
    emoji: str | None = None
    theme: str | None = None
    creature: str | None = None
    vibe: str | None = None
    avatar: str | None = None


IDENTITY_PLACEHOLDER_VALUES: set[str] = {
    "pick something you like",
    "ai? robot? familiar? ghost in the machine? something weirder?",
    "how do you come across? sharp? warm? chaotic? calm?",
    "your signature - pick one that feels right",
    "workspace-relative path, http(s) url, or data uri",
}


def _normalize_identity_value(value: str) -> str:
    normalized = value.strip()
    normalized = re.sub(r"^[*_]+|[*_]+$", "", normalized).strip()
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1].strip()
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = re.sub(r"\s+", " ", normalized).lower()
    return normalized


def _is_identity_placeholder(value: str) -> bool:
    return _normalize_identity_value(value) in IDENTITY_PLACEHOLDER_VALUES


def parse_identity_markdown(content: str) -> AgentIdentityFile:
    """Parse an IDENTITY.md file and extract identity fields."""
    identity = AgentIdentityFile()
    for line in content.splitlines():
        cleaned = re.sub(r"^\s*-\s*", "", line.strip())
        colon_idx = cleaned.find(":")
        if colon_idx == -1:
            continue
        label = cleaned[:colon_idx].replace("*", "").replace("_", "").strip().lower()
        value = re.sub(r"^[*_]+|[*_]+$", "", cleaned[colon_idx + 1:]).strip()
        if not value:
            continue
        if _is_identity_placeholder(value):
            continue
        if label == "name":
            identity.name = value
        elif label == "emoji":
            identity.emoji = value
        elif label == "creature":
            identity.creature = value
        elif label == "vibe":
            identity.vibe = value
        elif label == "theme":
            identity.theme = value
        elif label == "avatar":
            identity.avatar = value
    return identity


def identity_has_values(identity: AgentIdentityFile) -> bool:
    return bool(
        identity.name
        or identity.emoji
        or identity.theme
        or identity.creature
        or identity.vibe
        or identity.avatar
    )


def load_identity_from_file(identity_path: str) -> AgentIdentityFile | None:
    """Load and parse an IDENTITY.md file. Returns None if missing or empty."""
    try:
        with open(identity_path, "r", encoding="utf-8") as f:
            content = f.read()
        parsed = parse_identity_markdown(content)
        if not identity_has_values(parsed):
            return None
        return parsed
    except (OSError, IOError):
        return None


def load_agent_identity_from_workspace(
    workspace: str,
    identity_filename: str = "IDENTITY.md",
) -> AgentIdentityFile | None:
    """Load IDENTITY.md from a workspace directory."""
    identity_path = os.path.join(workspace, identity_filename)
    return load_identity_from_file(identity_path)

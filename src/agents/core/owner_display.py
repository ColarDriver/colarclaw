"""Owner display — ported from bk/src/agents/owner-display.ts.

Formatting owner/user display names for UI.
"""
from __future__ import annotations

from typing import Any


def format_owner_display_name(
    owner: dict[str, Any] | None = None,
    fallback: str = "Unknown",
) -> str:
    """Format an owner's display name."""
    if not owner:
        return fallback

    name = owner.get("name") or owner.get("displayName")
    if isinstance(name, str) and name.strip():
        return name.strip()

    email = owner.get("email")
    if isinstance(email, str) and email.strip():
        # Use part before @
        return email.split("@")[0].strip()

    username = owner.get("username") or owner.get("login")
    if isinstance(username, str) and username.strip():
        return username.strip()

    account_id = owner.get("accountId") or owner.get("id")
    if account_id:
        return str(account_id)[:8]

    return fallback


def format_owner_badge(owner: dict[str, Any] | None = None) -> str:
    """Format a compact owner badge for inline display."""
    name = format_owner_display_name(owner)
    return f"[{name}]"

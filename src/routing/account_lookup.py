"""Account lookup — ported from bk/src/routing/account-lookup.ts.

Case-insensitive account entry resolution.
"""
from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


def resolve_account_entry(
    accounts: dict[str, T] | None,
    account_id: str,
) -> T | None:
    """Resolve an account entry by ID (case-insensitive fallback)."""
    if not accounts or not isinstance(accounts, dict):
        return None
    if account_id in accounts:
        return accounts[account_id]
    normalized = account_id.lower()
    for key, value in accounts.items():
        if key.lower() == normalized:
            return value
    return None

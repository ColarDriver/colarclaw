"""Channels account — ported from bk/src/channels/account-snapshot-fields.ts,
account-summary.ts, read-only-account-inspect.ts.

Account snapshot field extraction, summary formatting, and read-only inspection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─── account snapshot fields ───

@dataclass
class AccountSnapshotField:
    key: str
    label: str
    value: str
    sensitive: bool = False
    multi_line: bool = False


@dataclass
class AccountSnapshot:
    channel: str = ""
    account_id: str = ""
    fields: list[AccountSnapshotField] = field(default_factory=list)
    status: str = ""  # "connected" | "disconnected" | "error"


def extract_account_snapshot_field(
    data: dict[str, Any],
    key: str,
    label: str,
    sensitive: bool = False,
    multi_line: bool = False,
) -> AccountSnapshotField | None:
    """Extract a snapshot field from account data."""
    value = data.get(key)
    if value is None:
        return None
    return AccountSnapshotField(
        key=key, label=label,
        value=str(value),
        sensitive=sensitive, multi_line=multi_line,
    )


def build_account_snapshot(
    channel: str,
    account_id: str,
    data: dict[str, Any],
    field_defs: list[tuple[str, str, bool, bool]],
    status: str = "connected",
) -> AccountSnapshot:
    """Build an account snapshot from data and field definitions."""
    fields = []
    for key, label, sensitive, multi_line in field_defs:
        f = extract_account_snapshot_field(data, key, label, sensitive, multi_line)
        if f:
            fields.append(f)
    return AccountSnapshot(channel=channel, account_id=account_id, fields=fields, status=status)


# ─── account-summary.ts ───

def format_account_summary(
    channel: str,
    account_id: str,
    status: str = "connected",
    detail: str = "",
) -> str:
    """Format a human-readable account summary line."""
    base = f"{channel}"
    if account_id:
        base += f" ({account_id})"
    if detail:
        base += f" — {detail}"
    if status and status != "connected":
        base += f" [{status}]"
    return base


# ─── read-only-account-inspect.ts ───

def inspect_account_read_only(
    cfg: dict[str, Any],
    channel: str,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Read-only account inspection from config."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    if not account_id:
        return {"config": channel_cfg}
    accounts = channel_cfg.get("accounts", {})
    acct = accounts.get(account_id, {})
    return {"config": {**channel_cfg, **acct}, "accountId": account_id}

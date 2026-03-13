"""Channels plugins.group_policy_warnings — ported from bk/src/channels/plugins/group-policy-warnings.ts.

Group policy validation warnings for misconfigured channels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GroupPolicyWarning:
    channel: str = ""
    account_id: str = ""
    kind: str = ""  # "unreachable" | "implicit-open" | "redundant" | "misconfigured"
    message: str = ""
    fix: str = ""


def check_group_policy_warnings(
    cfg: dict[str, Any],
    channel: str,
    account_id: str = "",
) -> list[GroupPolicyWarning]:
    """Check for group policy configuration warnings."""
    warnings: list[GroupPolicyWarning] = []
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})

    groups = channel_cfg.get("groups", {})
    group_policy = channel_cfg.get("groupPolicy")
    dm_policy = channel_cfg.get("dmPolicy")

    # Unreachable groups config when groupPolicy is "none"
    if group_policy == "none" and groups:
        warnings.append(GroupPolicyWarning(
            channel=channel, account_id=account_id,
            kind="unreachable",
            message=f"channels.{channel}.groups has entries but groupPolicy is 'none'",
            fix=f"Set channels.{channel}.groupPolicy to 'allowlist' or 'open'",
        ))

    # Implicit open when no groupPolicy set but groups exist
    if not group_policy and groups and len(groups) > 0:
        warnings.append(GroupPolicyWarning(
            channel=channel, account_id=account_id,
            kind="implicit-open",
            message=f"channels.{channel}.groups is configured but groupPolicy is not set (defaults to open)",
            fix=f"Set channels.{channel}.groupPolicy explicitly",
        ))

    # Redundant wildcard in allowFrom with open DM policy
    allow_from = channel_cfg.get("allowFrom", [])
    if dm_policy == "open" and isinstance(allow_from, list):
        non_wildcard = [e for e in allow_from if str(e).strip() != "*"]
        if non_wildcard:
            warnings.append(GroupPolicyWarning(
                channel=channel, account_id=account_id,
                kind="redundant",
                message=f"channels.{channel}.allowFrom has entries but dmPolicy is 'open'",
                fix=f"Set dmPolicy to 'allowlist' or remove allowFrom entries",
            ))

    return warnings

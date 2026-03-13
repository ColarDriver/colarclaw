"""Plugin SDK group access — ported from bk/src/plugin-sdk/group-access.ts.

Group access evaluation: sender-based, route-based, and matched-group access decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

SenderGroupAccessReason = Literal["allowed", "disabled", "empty_allowlist", "sender_not_allowlisted"]
GroupRouteAccessReason = Literal["allowed", "disabled", "empty_allowlist", "route_not_allowlisted", "route_disabled"]
MatchedGroupAccessReason = Literal["allowed", "disabled", "missing_match_input", "empty_allowlist", "not_allowlisted"]

GroupPolicy = Literal["open", "allowlist", "disabled"]


@dataclass
class SenderGroupAccessDecision:
    allowed: bool = False
    group_policy: GroupPolicy = "open"
    provider_missing_fallback_applied: bool = False
    reason: SenderGroupAccessReason = "allowed"


@dataclass
class GroupRouteAccessDecision:
    allowed: bool = False
    group_policy: GroupPolicy = "open"
    reason: GroupRouteAccessReason = "allowed"


@dataclass
class MatchedGroupAccessDecision:
    allowed: bool = False
    group_policy: GroupPolicy = "open"
    reason: MatchedGroupAccessReason = "allowed"


def resolve_sender_scoped_group_policy(group_policy: GroupPolicy, group_allow_from: list[str]) -> GroupPolicy:
    if group_policy == "disabled":
        return "disabled"
    return "allowlist" if group_allow_from else "open"


def evaluate_group_route_access_for_policy(
    group_policy: GroupPolicy,
    route_allowlist_configured: bool,
    route_matched: bool,
    route_enabled: bool | None = None,
) -> GroupRouteAccessDecision:
    if group_policy == "disabled":
        return GroupRouteAccessDecision(allowed=False, group_policy=group_policy, reason="disabled")
    if route_matched and route_enabled is False:
        return GroupRouteAccessDecision(allowed=False, group_policy=group_policy, reason="route_disabled")
    if group_policy == "allowlist":
        if not route_allowlist_configured:
            return GroupRouteAccessDecision(allowed=False, group_policy=group_policy, reason="empty_allowlist")
        if not route_matched:
            return GroupRouteAccessDecision(allowed=False, group_policy=group_policy, reason="route_not_allowlisted")
    return GroupRouteAccessDecision(allowed=True, group_policy=group_policy, reason="allowed")


def evaluate_matched_group_access_for_policy(
    group_policy: GroupPolicy,
    allowlist_configured: bool,
    allowlist_matched: bool,
    require_match_input: bool = False,
    has_match_input: bool = True,
) -> MatchedGroupAccessDecision:
    if group_policy == "disabled":
        return MatchedGroupAccessDecision(allowed=False, group_policy=group_policy, reason="disabled")
    if group_policy == "allowlist":
        if require_match_input and not has_match_input:
            return MatchedGroupAccessDecision(allowed=False, group_policy=group_policy, reason="missing_match_input")
        if not allowlist_configured:
            return MatchedGroupAccessDecision(allowed=False, group_policy=group_policy, reason="empty_allowlist")
        if not allowlist_matched:
            return MatchedGroupAccessDecision(allowed=False, group_policy=group_policy, reason="not_allowlisted")
    return MatchedGroupAccessDecision(allowed=True, group_policy=group_policy, reason="allowed")


def evaluate_sender_group_access_for_policy(
    group_policy: GroupPolicy,
    group_allow_from: list[str],
    sender_id: str,
    is_sender_allowed: Callable[[str, list[str]], bool],
    provider_missing_fallback_applied: bool = False,
) -> SenderGroupAccessDecision:
    if group_policy == "disabled":
        return SenderGroupAccessDecision(
            allowed=False, group_policy=group_policy,
            provider_missing_fallback_applied=provider_missing_fallback_applied,
            reason="disabled",
        )
    if group_policy == "allowlist":
        if not group_allow_from:
            return SenderGroupAccessDecision(
                allowed=False, group_policy=group_policy,
                provider_missing_fallback_applied=provider_missing_fallback_applied,
                reason="empty_allowlist",
            )
        if not is_sender_allowed(sender_id, group_allow_from):
            return SenderGroupAccessDecision(
                allowed=False, group_policy=group_policy,
                provider_missing_fallback_applied=provider_missing_fallback_applied,
                reason="sender_not_allowlisted",
            )
    return SenderGroupAccessDecision(
        allowed=True, group_policy=group_policy,
        provider_missing_fallback_applied=provider_missing_fallback_applied,
        reason="allowed",
    )


def evaluate_sender_group_access(
    provider_config_present: bool,
    group_allow_from: list[str],
    sender_id: str,
    is_sender_allowed: Callable[[str, list[str]], bool],
    configured_group_policy: GroupPolicy | None = None,
    default_group_policy: GroupPolicy | None = None,
) -> SenderGroupAccessDecision:
    group_policy = configured_group_policy or default_group_policy or "open"
    fallback_applied = not provider_config_present and configured_group_policy is None
    return evaluate_sender_group_access_for_policy(
        group_policy=group_policy, group_allow_from=group_allow_from,
        sender_id=sender_id, is_sender_allowed=is_sender_allowed,
        provider_missing_fallback_applied=fallback_applied,
    )

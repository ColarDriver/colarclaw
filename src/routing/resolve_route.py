"""Agent route resolution — ported from bk/src/routing/resolve-route.ts.

Full agent routing engine with binding evaluation, tier-based matching,
peer/guild/team/role resolution, and session key construction.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal

from .account_id import DEFAULT_ACCOUNT_ID, normalize_account_id
from .bindings import list_bindings
from .session_key import (
    DEFAULT_AGENT_ID,
    DEFAULT_MAIN_KEY,
    build_agent_main_session_key,
    build_agent_peer_session_key,
    normalize_agent_id,
    sanitize_agent_id,
)

logger = logging.getLogger(__name__)

MatchedBy = Literal[
    "binding.peer",
    "binding.peer.parent",
    "binding.guild+roles",
    "binding.guild",
    "binding.team",
    "binding.account",
    "binding.channel",
    "default",
]


@dataclass
class RoutePeer:
    kind: str  # "direct" | "group" | "channel"
    id: str


@dataclass
class ResolvedAgentRoute:
    agent_id: str = ""
    channel: str = ""
    account_id: str = ""
    session_key: str = ""
    main_session_key: str = ""
    last_route_policy: str = "main"  # "main" | "session"
    matched_by: MatchedBy = "default"


@dataclass
class ResolveAgentRouteInput:
    cfg: dict[str, Any] = field(default_factory=dict)
    channel: str = ""
    account_id: str | None = None
    peer: RoutePeer | None = None
    parent_peer: RoutePeer | None = None
    guild_id: str | None = None
    team_id: str | None = None
    member_role_ids: list[str] = field(default_factory=list)


# ─── helpers ───

def _normalize_token(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_id(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(int(value)).strip()
    return ""


def derive_last_route_policy(session_key: str, main_session_key: str) -> str:
    return "main" if session_key == main_session_key else "session"


# ─── binding evaluation ───

@dataclass
class _NormalizedPeerConstraint:
    state: str  # "none" | "invalid" | "valid"
    kind: str = ""
    id: str = ""


@dataclass
class _NormalizedBindingMatch:
    account_pattern: str = ""
    peer: _NormalizedPeerConstraint = field(
        default_factory=lambda: _NormalizedPeerConstraint(state="none")
    )
    guild_id: str | None = None
    team_id: str | None = None
    roles: list[str] | None = None


@dataclass
class _EvaluatedBinding:
    binding: dict[str, Any] = field(default_factory=dict)
    match: _NormalizedBindingMatch = field(default_factory=_NormalizedBindingMatch)
    order: int = 0


def _normalize_peer_constraint(peer: dict[str, Any] | None) -> _NormalizedPeerConstraint:
    if not peer:
        return _NormalizedPeerConstraint(state="none")
    kind = _normalize_token(peer.get("kind"))
    pid = _normalize_id(peer.get("id"))
    if not kind or not pid:
        return _NormalizedPeerConstraint(state="invalid")
    return _NormalizedPeerConstraint(state="valid", kind=kind, id=pid)


def _normalize_binding_match(match: dict[str, Any] | None) -> _NormalizedBindingMatch:
    if not match:
        return _NormalizedBindingMatch()
    raw_roles = match.get("roles")
    return _NormalizedBindingMatch(
        account_pattern=(match.get("accountId") or "").strip(),
        peer=_normalize_peer_constraint(match.get("peer")),
        guild_id=_normalize_id(match.get("guildId")) or None,
        team_id=_normalize_id(match.get("teamId")) or None,
        roles=raw_roles if isinstance(raw_roles, list) and raw_roles else None,
    )


def _peer_kind_matches(binding_kind: str, scope_kind: str) -> bool:
    if binding_kind == scope_kind:
        return True
    both = {binding_kind, scope_kind}
    return "group" in both and "channel" in both


def _matches_binding_scope(
    match: _NormalizedBindingMatch,
    peer: RoutePeer | None,
    guild_id: str,
    team_id: str,
    role_ids: set[str],
) -> bool:
    if match.peer.state == "invalid":
        return False
    if match.peer.state == "valid":
        if not peer or not _peer_kind_matches(match.peer.kind, peer.kind) or peer.id != match.peer.id:
            return False
    if match.guild_id and match.guild_id != guild_id:
        return False
    if match.team_id and match.team_id != team_id:
        return False
    if match.roles:
        return any(r in role_ids for r in match.roles)
    return True


def _build_evaluated_bindings(cfg: dict[str, Any], channel: str, account_id: str) -> list[_EvaluatedBinding]:
    """Build the evaluated bindings list for a channel+account."""
    result: list[_EvaluatedBinding] = []
    order = 0
    for binding in list_bindings(cfg):
        if not binding or not isinstance(binding, dict):
            continue
        match_raw = binding.get("match")
        if not match_raw or not isinstance(match_raw, dict):
            continue
        ch = _normalize_token(match_raw.get("channel"))
        if ch != channel:
            continue
        match = _normalize_binding_match(match_raw)
        # Filter by account
        if match.account_pattern and match.account_pattern != "*":
            acct_key = normalize_account_id(match.account_pattern)
            if acct_key != account_id and acct_key != DEFAULT_ACCOUNT_ID:
                continue
        result.append(_EvaluatedBinding(binding=binding, match=match, order=order))
        order += 1
    return result


def _pick_first_existing_agent_id(cfg: dict[str, Any], agent_id: str) -> str:
    """Pick the first existing agent ID that matches, or default."""
    trimmed = (agent_id or "").strip()
    agents_list = cfg.get("agents", {}).get("list", [])
    if not isinstance(agents_list, list) or not agents_list:
        return sanitize_agent_id(trimmed) if trimmed else DEFAULT_AGENT_ID

    normalized = normalize_agent_id(trimmed) if trimmed else ""
    for agent in agents_list:
        if isinstance(agent, dict):
            raw_id = (agent.get("id") or "").strip()
            if raw_id and normalize_agent_id(raw_id) == normalized:
                return sanitize_agent_id(raw_id)

    # Fallback to default
    default_id = cfg.get("agents", {}).get("default", "")
    if isinstance(default_id, str) and default_id.strip():
        return sanitize_agent_id(default_id)
    if agents_list and isinstance(agents_list[0], dict):
        fid = agents_list[0].get("id", "")
        if isinstance(fid, str) and fid.strip():
            return sanitize_agent_id(fid)
    return DEFAULT_AGENT_ID


# ─── main resolver ───

def resolve_agent_route(input_data: ResolveAgentRouteInput | dict[str, Any]) -> ResolvedAgentRoute:
    """Resolve which agent should handle a message.

    Tier-based matching:
      1. binding.peer       — exact peer match
      2. binding.peer.parent — parent peer (thread inheritance)
      3. binding.guild+roles — guild + role match
      4. binding.guild       — guild-only match
      5. binding.team        — team match
      6. binding.account     — account-scoped match
      7. binding.channel     — channel-wide match
      8. default             — default agent
    """
    if isinstance(input_data, dict):
        inp = ResolveAgentRouteInput(**input_data)
    else:
        inp = input_data

    cfg = inp.cfg
    channel = _normalize_token(inp.channel)
    account_id = normalize_account_id(inp.account_id)
    peer = inp.peer
    parent_peer = inp.parent_peer
    guild_id = _normalize_id(inp.guild_id)
    team_id = _normalize_id(inp.team_id)
    role_ids = set(inp.member_role_ids)
    dm_scope = cfg.get("session", {}).get("dmScope", "main") if isinstance(cfg.get("session"), dict) else "main"
    identity_links = cfg.get("session", {}).get("identityLinks") if isinstance(cfg.get("session"), dict) else None

    def choose(agent_id: str, matched_by: MatchedBy) -> ResolvedAgentRoute:
        resolved_id = _pick_first_existing_agent_id(cfg, agent_id)
        session_key = build_agent_peer_session_key(
            agent_id=resolved_id,
            channel=channel,
            account_id=account_id,
            peer_kind=peer.kind if peer else "direct",
            peer_id=peer.id if peer else None,
            dm_scope=dm_scope,
            identity_links=identity_links,
        ).lower()
        main_key = build_agent_main_session_key(resolved_id).lower()
        return ResolvedAgentRoute(
            agent_id=resolved_id,
            channel=channel,
            account_id=account_id,
            session_key=session_key,
            main_session_key=main_key,
            last_route_policy=derive_last_route_policy(session_key, main_key),
            matched_by=matched_by,
        )

    bindings = _build_evaluated_bindings(cfg, channel, account_id)

    # Tier matching
    tiers: list[tuple[MatchedBy, bool, RoutePeer | None, list[_EvaluatedBinding]]] = [
        ("binding.peer", bool(peer), peer, [
            b for b in bindings if b.match.peer.state == "valid"
        ]),
        ("binding.peer.parent", bool(parent_peer and parent_peer.id), parent_peer, [
            b for b in bindings if b.match.peer.state == "valid"
        ]),
        ("binding.guild+roles", bool(guild_id and role_ids), peer, [
            b for b in bindings if b.match.guild_id and b.match.roles
        ]),
        ("binding.guild", bool(guild_id), peer, [
            b for b in bindings if b.match.guild_id and not b.match.roles
        ]),
        ("binding.team", bool(team_id), peer, [
            b for b in bindings if b.match.team_id
        ]),
        ("binding.account", True, peer, [
            b for b in bindings if b.match.account_pattern and b.match.account_pattern != "*"
        ]),
        ("binding.channel", True, peer, [
            b for b in bindings if b.match.account_pattern == "*" or not b.match.account_pattern
        ]),
    ]

    for matched_by, enabled, scope_peer, candidates in tiers:
        if not enabled:
            continue
        for candidate in candidates:
            if _matches_binding_scope(
                candidate.match,
                scope_peer,
                guild_id,
                team_id,
                role_ids,
            ):
                return choose(candidate.binding.get("agentId", ""), matched_by)

    # Default
    default_agent = _pick_first_existing_agent_id(cfg, "")
    return choose(default_agent, "default")

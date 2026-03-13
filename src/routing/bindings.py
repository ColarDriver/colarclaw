"""Bindings — ported from bk/src/routing/bindings.ts.

Agent-to-channel binding resolution, account listing, and preference.
"""
from __future__ import annotations

from typing import Any

from .account_id import normalize_account_id
from .session_key import normalize_agent_id


def _normalize_binding_channel_id(raw: str | None) -> str | None:
    """Normalize a binding channel ID."""
    fallback = (raw or "").strip().lower()
    return fallback or None


def list_bindings(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """List all route bindings from config."""
    bindings = cfg.get("bindings", [])
    return bindings if isinstance(bindings, list) else []


def list_bound_account_ids(cfg: dict[str, Any], channel_id: str) -> list[str]:
    """List bound account IDs for a given channel."""
    normalized_channel = _normalize_binding_channel_id(channel_id)
    if not normalized_channel:
        return []
    ids: set[str] = set()
    for binding in list_bindings(cfg):
        resolved = _resolve_normalized_binding_match(binding)
        if not resolved or resolved["channel_id"] != normalized_channel:
            continue
        ids.add(resolved["account_id"])
    return sorted(ids)


def resolve_default_agent_bound_account_id(
    cfg: dict[str, Any],
    channel_id: str,
) -> str | None:
    """Resolve the account ID bound to the default agent for a channel."""
    normalized_channel = _normalize_binding_channel_id(channel_id)
    if not normalized_channel:
        return None
    default_agent_id = normalize_agent_id(
        _resolve_default_agent_id(cfg)
    )
    for binding in list_bindings(cfg):
        resolved = _resolve_normalized_binding_match(binding)
        if (
            not resolved
            or resolved["channel_id"] != normalized_channel
            or resolved["agent_id"] != default_agent_id
        ):
            continue
        return resolved["account_id"]
    return None


def build_channel_account_bindings(
    cfg: dict[str, Any],
) -> dict[str, dict[str, list[str]]]:
    """Build a channel → agent → account IDs mapping."""
    result: dict[str, dict[str, list[str]]] = {}
    for binding in list_bindings(cfg):
        resolved = _resolve_normalized_binding_match(binding)
        if not resolved:
            continue
        ch = resolved["channel_id"]
        agent = resolved["agent_id"]
        if ch not in result:
            result[ch] = {}
        if agent not in result[ch]:
            result[ch][agent] = []
        if resolved["account_id"] not in result[ch][agent]:
            result[ch][agent].append(resolved["account_id"])
    return result


def resolve_preferred_account_id(
    account_ids: list[str],
    default_account_id: str,
    bound_accounts: list[str],
) -> str:
    """Resolve preferred account: bound first, then default."""
    if bound_accounts:
        return bound_accounts[0]
    return default_account_id


# ─── helpers ───

def _resolve_normalized_binding_match(
    binding: dict[str, Any],
) -> dict[str, str] | None:
    """Extract normalized match from a binding."""
    if not binding or not isinstance(binding, dict):
        return None
    match = binding.get("match")
    if not match or not isinstance(match, dict):
        return None
    channel_id = _normalize_binding_channel_id(match.get("channel"))
    if not channel_id:
        return None
    account_id = str(match.get("accountId", "")).strip()
    if not account_id or account_id == "*":
        return None
    return {
        "agent_id": normalize_agent_id(binding.get("agentId")),
        "account_id": normalize_account_id(account_id),
        "channel_id": channel_id,
    }


def _resolve_default_agent_id(cfg: dict[str, Any]) -> str:
    """Resolve the default agent ID from config."""
    agents = cfg.get("agents", {})
    if isinstance(agents, dict):
        default = agents.get("default")
        if isinstance(default, str) and default.strip():
            return default.strip()
        agent_list = agents.get("list", [])
        if isinstance(agent_list, list) and agent_list:
            first = agent_list[0]
            if isinstance(first, dict):
                fid = first.get("id", "")
                if isinstance(fid, str) and fid.strip():
                    return fid.strip()
    return "main"

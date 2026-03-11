"""Agent scope — ported from bk/src/agents/agent-scope.ts.

Resolves agent IDs, workspace directories, model primaries, fallbacks,
and skill filters from configuration.
"""
from __future__ import annotations
import logging
import os
from typing import Any
from agents.agent_paths import resolve_state_dir

log = logging.getLogger("openclaw.agents.agent_scope")
DEFAULT_AGENT_ID = "default"

def normalize_agent_id(raw: str | None) -> str:
    if not raw or not isinstance(raw, str):
        return DEFAULT_AGENT_ID
    trimmed = raw.strip().lower().replace("\x00", "")
    return trimmed or DEFAULT_AGENT_ID

def parse_agent_session_key(session_key: str) -> dict[str, str] | None:
    parts = session_key.split(":")
    if len(parts) >= 2 and parts[0] == "agent":
        return {"agentId": parts[1]}
    return None

def resolve_agent_id_from_session_key(session_key: str | None) -> str:
    if not session_key:
        return DEFAULT_AGENT_ID
    parsed = parse_agent_session_key(session_key.strip().lower())
    return normalize_agent_id(parsed["agentId"]) if parsed else DEFAULT_AGENT_ID

def list_agent_entries(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    lst = cfg.get("agents", {}).get("list")
    if not isinstance(lst, list):
        return []
    return [e for e in lst if isinstance(e, dict)]

def list_agent_ids(cfg: dict[str, Any]) -> list[str]:
    agents = list_agent_entries(cfg)
    if not agents:
        return [DEFAULT_AGENT_ID]
    seen: set[str] = set()
    ids: list[str] = []
    for entry in agents:
        aid = normalize_agent_id(entry.get("id"))
        if aid not in seen:
            seen.add(aid)
            ids.append(aid)
    return ids or [DEFAULT_AGENT_ID]

def resolve_default_agent_id(cfg: dict[str, Any]) -> str:
    agents = list_agent_entries(cfg)
    if not agents:
        return DEFAULT_AGENT_ID
    defaults = [a for a in agents if a.get("default")]
    if len(defaults) > 1:
        log.warning("Multiple agents marked default=true; using the first.")
    chosen = (defaults[0] if defaults else agents[0]).get("id", "")
    return normalize_agent_id(chosen or DEFAULT_AGENT_ID)

def resolve_session_agent_ids(
    session_key: str | None = None,
    config: dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> dict[str, str]:
    default_id = resolve_default_agent_id(config or {})
    explicit = normalize_agent_id(agent_id) if agent_id and agent_id.strip() else None
    parsed = parse_agent_session_key(session_key.strip().lower()) if session_key else None
    session_id = explicit or (normalize_agent_id(parsed["agentId"]) if parsed and parsed.get("agentId") else default_id)
    return {"defaultAgentId": default_id, "sessionAgentId": session_id}

def resolve_agent_config(cfg: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    aid = normalize_agent_id(agent_id)
    for entry in list_agent_entries(cfg):
        if normalize_agent_id(entry.get("id")) == aid:
            return entry
    return None

def resolve_agent_workspace_dir(cfg: dict[str, Any], agent_id: str) -> str:
    aid = normalize_agent_id(agent_id)
    entry = resolve_agent_config(cfg, aid)
    if entry and entry.get("workspace", "").strip():
        return os.path.expanduser(entry["workspace"].strip())
    default_id = resolve_default_agent_id(cfg)
    if aid == default_id:
        fallback = cfg.get("agents", {}).get("defaults", {}).get("workspace", "").strip()
        if fallback:
            return os.path.expanduser(fallback)
        return os.path.expanduser("~/.openclaw/workspace")
    return os.path.join(resolve_state_dir(), f"workspace-{aid}")

def resolve_agent_model_primary(cfg: dict[str, Any], agent_id: str) -> str | None:
    entry = resolve_agent_config(cfg, agent_id)
    raw = entry.get("model") if entry else None
    if isinstance(raw, str):
        return raw.strip() or None
    if isinstance(raw, dict):
        primary = raw.get("primary")
        return primary.strip() if isinstance(primary, str) and primary.strip() else None
    return None

def resolve_agent_effective_model_primary(cfg: dict[str, Any], agent_id: str) -> str | None:
    explicit = resolve_agent_model_primary(cfg, agent_id)
    if explicit:
        return explicit
    default_model = cfg.get("agents", {}).get("defaults", {}).get("model")
    if isinstance(default_model, str):
        return default_model.strip() or None
    if isinstance(default_model, dict):
        p = default_model.get("primary")
        return p.strip() if isinstance(p, str) and p.strip() else None
    return None

def resolve_agent_model_fallbacks_override(cfg: dict[str, Any], agent_id: str) -> list[str] | None:
    entry = resolve_agent_config(cfg, agent_id)
    raw = entry.get("model") if entry else None
    if not raw or isinstance(raw, str):
        return None
    if isinstance(raw, dict) and "fallbacks" in raw:
        fb = raw["fallbacks"]
        return fb if isinstance(fb, list) else None
    return None

def resolve_agent_dir(cfg: dict[str, Any], agent_id: str) -> str:
    aid = normalize_agent_id(agent_id)
    entry = resolve_agent_config(cfg, aid)
    if entry and entry.get("agentDir", "").strip():
        return os.path.expanduser(entry["agentDir"].strip())
    return os.path.join(resolve_state_dir(), "agents", aid, "agent")

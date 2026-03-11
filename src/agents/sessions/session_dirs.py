"""Session directories — ported from bk/src/agents/session-dirs.ts."""
from __future__ import annotations
import os
from agents.agent_paths import resolve_state_dir

def resolve_sessions_dir(agent_id: str = "default") -> str:
    return os.path.join(resolve_state_dir(), "agents", agent_id, "sessions")

def resolve_session_file(agent_id: str, session_slug: str) -> str:
    return os.path.join(resolve_sessions_dir(agent_id), f"{session_slug}.jsonl")

def resolve_session_file_from_key(session_key: str) -> str:
    from agents.agent_scope import resolve_agent_id_from_session_key
    from agents.session_slug import session_key_to_slug
    agent_id = resolve_agent_id_from_session_key(session_key)
    slug = session_key_to_slug(session_key)
    return resolve_session_file(agent_id, slug)

def ensure_sessions_dir(agent_id: str = "default") -> str:
    d = resolve_sessions_dir(agent_id)
    os.makedirs(d, exist_ok=True)
    return d

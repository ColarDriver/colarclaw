"""Agent paths — ported from bk/src/agents/agent-paths.ts."""
from __future__ import annotations
import os

DEFAULT_AGENT_ID = "default"

def resolve_state_dir() -> str:
    return os.environ.get("OPENCLAW_STATE_DIR", os.path.expanduser("~/.openclaw"))

def resolve_openclaw_agent_dir() -> str:
    override = (os.environ.get("OPENCLAW_AGENT_DIR") or os.environ.get("PI_CODING_AGENT_DIR") or "").strip()
    if override:
        return os.path.expanduser(override)
    return os.path.expanduser(os.path.join(resolve_state_dir(), "agents", DEFAULT_AGENT_ID, "agent"))

def ensure_openclaw_agent_env() -> str:
    d = resolve_openclaw_agent_dir()
    if not os.environ.get("OPENCLAW_AGENT_DIR"):
        os.environ["OPENCLAW_AGENT_DIR"] = d
    if not os.environ.get("PI_CODING_AGENT_DIR"):
        os.environ["PI_CODING_AGENT_DIR"] = d
    return d

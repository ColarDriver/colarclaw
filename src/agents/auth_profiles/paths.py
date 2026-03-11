"""Auth profile paths — ported from bk/src/agents/auth-profiles/paths.ts."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .constants import AUTH_PROFILE_FILENAME, AUTH_STORE_VERSION, LEGACY_AUTH_FILENAME


def _resolve_agent_dir() -> str:
    """Resolve the OpenClaw agent directory."""
    return os.path.join(str(Path.home()), ".openclaw")


def resolve_auth_store_path(agent_dir: str | None = None) -> str:
    resolved = agent_dir or _resolve_agent_dir()
    resolved = os.path.expanduser(resolved)
    return os.path.join(resolved, AUTH_PROFILE_FILENAME)


def resolve_legacy_auth_store_path(agent_dir: str | None = None) -> str:
    resolved = agent_dir or _resolve_agent_dir()
    resolved = os.path.expanduser(resolved)
    return os.path.join(resolved, LEGACY_AUTH_FILENAME)


def resolve_auth_store_path_for_display(agent_dir: str | None = None) -> str:
    return resolve_auth_store_path(agent_dir)


def ensure_auth_store_file(pathname: str) -> None:
    if os.path.exists(pathname):
        return
    os.makedirs(os.path.dirname(pathname), exist_ok=True)
    payload = {"version": AUTH_STORE_VERSION, "profiles": {}}
    with open(pathname, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

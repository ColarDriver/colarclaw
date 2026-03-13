"""Configuration file path resolution.

Ported from bk/src/config/paths.ts (284 lines), config-paths.ts.

Resolves config file location, state/data directories, and default candidates.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Default config file names in priority order
CONFIG_FILE_NAMES = [
    "openclaw.json5",
    "openclaw.json",
    ".openclaw.json5",
    ".openclaw.json",
]

DEFAULT_STATE_DIR_NAME = ".openclaw"
DEFAULT_PORT = 18789


def resolve_home_dir(env: dict[str, str] | None = None) -> str:
    """Resolve the user's home directory."""
    e = env or os.environ
    # Check explicit override
    home = e.get("OPENCLAW_HOME")
    if home and home.strip():
        return home.strip()
    return str(Path.home())


def resolve_state_dir(
    env: dict[str, str] | None = None,
    homedir: str | None = None,
) -> str:
    """Resolve the OpenClaw state directory (~/.openclaw)."""
    e = env or os.environ

    # Explicit override
    state_dir = e.get("OPENCLAW_STATE_DIR")
    if state_dir and state_dir.strip():
        return state_dir.strip()

    home = homedir or resolve_home_dir(e)
    return os.path.join(home, DEFAULT_STATE_DIR_NAME)


def resolve_config_path(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the primary config file path.

    Checks OPENCLAW_CONFIG env var first, then falls back to
    the first existing candidate in the state directory.
    """
    e = env or os.environ

    # Explicit config path
    config_path = e.get("OPENCLAW_CONFIG")
    if config_path and config_path.strip():
        return config_path.strip()

    sd = state_dir or resolve_state_dir(e)
    # Check for existing config files
    for name in CONFIG_FILE_NAMES:
        candidate = os.path.join(sd, name)
        if os.path.exists(candidate):
            return candidate

    # Default to first candidate
    return os.path.join(sd, CONFIG_FILE_NAMES[0])


def resolve_default_config_candidates(
    env: dict[str, str] | None = None,
    homedir: str | None = None,
) -> list[str]:
    """Resolve all candidate config file paths to check."""
    e = env or os.environ
    sd = resolve_state_dir(e, homedir)
    return [os.path.join(sd, name) for name in CONFIG_FILE_NAMES]


def resolve_sessions_dir(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the sessions storage directory."""
    sd = state_dir or resolve_state_dir(env)
    return os.path.join(sd, "sessions")


def resolve_agents_dir(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the agents data directory."""
    sd = state_dir or resolve_state_dir(env)
    return os.path.join(sd, "agents")


def resolve_plugins_dir(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the plugins directory."""
    sd = state_dir or resolve_state_dir(env)
    return os.path.join(sd, "plugins")


def resolve_credentials_dir(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the credentials directory."""
    sd = state_dir or resolve_state_dir(env)
    return os.path.join(sd, "credentials")


def resolve_logs_dir(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the logs directory."""
    sd = state_dir or resolve_state_dir(env)
    return os.path.join(sd, "logs")


def resolve_cache_dir(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the cache directory."""
    e = env or os.environ
    cache = e.get("OPENCLAW_CACHE_DIR")
    if cache and cache.strip():
        return cache.strip()
    sd = state_dir or resolve_state_dir(e)
    return os.path.join(sd, "cache")


def resolve_backup_dir(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the config backup directory."""
    sd = state_dir or resolve_state_dir(env)
    return os.path.join(sd, "backups")


def resolve_config_audit_log_path(
    env: dict[str, str] | None = None,
    state_dir: str | None = None,
) -> str:
    """Resolve the config audit log file path."""
    logs = resolve_logs_dir(env, state_dir)
    return os.path.join(logs, "config-audit.jsonl")

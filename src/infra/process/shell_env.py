"""Infra shell env — ported from bk/src/infra/shell-env.ts, shell-inline-command.ts,
host-env-security.ts, path-env.ts, path-prepend.ts, path-guards.ts,
path-alias-guards.ts, path-safety.ts, stable-node-path.ts, node-shell.ts.

Shell environment fallback, PATH manipulation, host env security,
path validation, inline command resolution.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("infra.shell_env")

DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_BUFFER = 2 * 1024 * 1024
DEFAULT_SHELL = "/bin/sh"

_last_applied_keys: list[str] = []
_cached_shell_path: str | None | None = None
_cached_etc_shells: set[str] | None = None


# ─── host-env-security.ts ───

# Environment keys that should be stripped from child processes
_BLOCKED_ENV_KEYS = {
    "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS",
}

# Keys that are safe to passthrough
_PASSTHROUGH_PREFIXES = ("OPENCLAW_", "HOME", "USER", "PATH", "SHELL", "LANG", "LC_",
                          "TERM", "COLORTERM", "FORCE_COLOR", "NO_COLOR", "XDG_", "SSH_AUTH_SOCK")


def sanitize_host_exec_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Remove potentially dangerous env vars from child process environment."""
    env = dict(base_env or os.environ)
    for key in _BLOCKED_ENV_KEYS:
        env.pop(key, None)
    return env


def is_env_key_safe(key: str) -> bool:
    if key in _BLOCKED_ENV_KEYS:
        return False
    return any(key.startswith(prefix) for prefix in _PASSTHROUGH_PREFIXES)


# ─── path-env.ts ───

def get_path_entries(env: dict[str, str] | None = None) -> list[str]:
    """Get PATH entries as a list."""
    path_str = (env or os.environ).get("PATH", "")
    return [p for p in path_str.split(os.pathsep) if p.strip()]


def set_path_entries(entries: list[str], env: dict[str, str] | None = None) -> None:
    """Set PATH entries from a list."""
    target = env if env is not None else os.environ
    target["PATH"] = os.pathsep.join(entries)


def dedupe_path_entries(entries: list[str]) -> list[str]:
    """Deduplicate PATH entries preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for entry in entries:
        normalized = os.path.normpath(entry)
        if normalized not in seen:
            seen.add(normalized)
            result.append(entry)
    return result


# ─── path-prepend.ts ───

def prepend_to_path(directory: str, env: dict[str, str] | None = None) -> None:
    """Prepend a directory to PATH if not already present."""
    entries = get_path_entries(env)
    normalized = os.path.normpath(directory)
    if not any(os.path.normpath(e) == normalized for e in entries):
        entries.insert(0, directory)
        set_path_entries(entries, env)


def append_to_path(directory: str, env: dict[str, str] | None = None) -> None:
    """Append a directory to PATH if not already present."""
    entries = get_path_entries(env)
    normalized = os.path.normpath(directory)
    if not any(os.path.normpath(e) == normalized for e in entries):
        entries.append(directory)
        set_path_entries(entries, env)


# ─── path-guards.ts ───

def is_safe_path(path_str: str) -> bool:
    """Check if a path is safe (no traversal, no null bytes)."""
    if "\0" in path_str:
        return False
    normalized = os.path.normpath(path_str)
    if ".." in normalized.split(os.sep):
        return False
    return True


def guard_path_traversal(path_str: str, boundary: str) -> bool:
    """Ensure path stays within boundary directory."""
    abs_path = os.path.abspath(path_str)
    abs_boundary = os.path.abspath(boundary)
    return abs_path.startswith(abs_boundary + os.sep) or abs_path == abs_boundary


# ─── path-alias-guards.ts ───

_PATH_ALIAS_PATTERNS = [
    re.compile(r"^~"),  # home alias
    re.compile(r"\$\{?\w+\}?"),  # env var expansion
    re.compile(r"`.*`"),  # backtick substitution
    re.compile(r"\$\(.*\)"),  # command substitution
]


def has_path_alias(path_str: str) -> bool:
    """Check if path contains aliases or substitutions."""
    return any(p.search(path_str) for p in _PATH_ALIAS_PATTERNS)


def resolve_path_aliases(path_str: str) -> str:
    """Resolve ~ and environment variable aliases."""
    return os.path.expandvars(os.path.expanduser(path_str))


# ─── path-safety.ts ───

def is_path_safe_for_exec(path_str: str) -> bool:
    """Check if a path is safe for command execution."""
    if not path_str or not path_str.strip():
        return False
    if "\0" in path_str:
        return False
    if has_path_alias(path_str):
        return False
    return is_safe_path(path_str)


# ─── shell-env.ts: login shell environment ───

def _read_etc_shells() -> set[str] | None:
    global _cached_etc_shells
    if _cached_etc_shells is not None:
        return _cached_etc_shells
    try:
        with open("/etc/shells", "r") as f:
            raw = f.read()
        entries = set()
        for line in raw.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and os.path.isabs(line):
                entries.add(line)
        _cached_etc_shells = entries
    except OSError:
        _cached_etc_shells = None  # type: ignore
        return None
    return _cached_etc_shells


def _is_trusted_shell_path(shell: str) -> bool:
    if not os.path.isabs(shell):
        return False
    normalized = os.path.normpath(shell)
    if normalized != shell:
        return False
    shells = _read_etc_shells()
    return shell in shells if shells else False


def _resolve_shell(env: dict[str, str] | None = None) -> str:
    shell = (env or os.environ).get("SHELL", "").strip()
    if shell and _is_trusted_shell_path(shell):
        return shell
    return DEFAULT_SHELL


def _probe_login_shell_env(
    env: dict[str, str] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, str] | None:
    """Probe login shell environment using `env -0`."""
    shell = _resolve_shell(env)
    exec_env = sanitize_host_exec_env(env)

    # Pin HOME to real user home
    home = str(Path.home())
    if home:
        exec_env["HOME"] = home
    else:
        exec_env.pop("HOME", None)

    # Avoid zsh startup-file redirection
    exec_env.pop("ZDOTDIR", None)

    try:
        result = subprocess.run(
            [shell, "-l", "-c", "env -0"],
            capture_output=True, timeout=timeout_s,
            env=exec_env,
        )
        if result.returncode != 0:
            return None
        shell_env: dict[str, str] = {}
        for part in result.stdout.decode(errors="replace").split("\0"):
            if not part:
                continue
            eq = part.find("=")
            if eq <= 0:
                continue
            key, value = part[:eq], part[eq + 1:]
            if key:
                shell_env[key] = value
        return shell_env
    except (subprocess.TimeoutExpired, OSError):
        return None


def load_shell_env_fallback(
    enabled: bool = True,
    expected_keys: list[str] | None = None,
    env: dict[str, str] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Load missing env vars from login shell."""
    global _last_applied_keys
    target_env = env if env is not None else dict(os.environ)

    if not enabled:
        _last_applied_keys = []
        return {"ok": True, "applied": [], "skipped_reason": "disabled"}

    keys = expected_keys or []
    has_any = any(target_env.get(k, "").strip() for k in keys)
    if has_any:
        _last_applied_keys = []
        return {"ok": True, "applied": [], "skipped_reason": "already-has-keys"}

    shell_env = _probe_login_shell_env(target_env, timeout_s)
    if shell_env is None:
        _last_applied_keys = []
        return {"ok": False, "error": "shell env probe failed", "applied": []}

    applied: list[str] = []
    for key in keys:
        if target_env.get(key, "").strip():
            continue
        value = shell_env.get(key, "").strip()
        if value:
            target_env[key] = value
            applied.append(key)

    _last_applied_keys = applied
    return {"ok": True, "applied": applied}


def should_enable_shell_env_fallback() -> bool:
    from ..env import is_truthy_env_value
    return is_truthy_env_value(os.environ.get("OPENCLAW_LOAD_SHELL_ENV"))


def should_defer_shell_env_fallback() -> bool:
    from ..env import is_truthy_env_value
    return is_truthy_env_value(os.environ.get("OPENCLAW_DEFER_SHELL_ENV_FALLBACK"))


def resolve_shell_env_fallback_timeout_s() -> float:
    raw = os.environ.get("OPENCLAW_SHELL_ENV_TIMEOUT_MS", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_S
    try:
        parsed = int(raw)
        return max(0, parsed) / 1000.0
    except ValueError:
        return DEFAULT_TIMEOUT_S


def get_shell_path_from_login_shell(timeout_s: float = DEFAULT_TIMEOUT_S) -> str | None:
    """Get PATH from login shell environment."""
    global _cached_shell_path
    if _cached_shell_path is not None:
        return _cached_shell_path if _cached_shell_path else None

    if sys.platform == "win32":
        _cached_shell_path = ""
        return None

    shell_env = _probe_login_shell_env(timeout_s=timeout_s)
    if not shell_env:
        _cached_shell_path = ""
        return None

    path = shell_env.get("PATH", "").strip()
    _cached_shell_path = path if path else ""
    return path if path else None


def get_shell_env_applied_keys() -> list[str]:
    return list(_last_applied_keys)


def reset_shell_path_cache_for_tests() -> None:
    global _cached_shell_path, _cached_etc_shells
    _cached_shell_path = None
    _cached_etc_shells = None


# ─── shell-inline-command.ts ───

def build_shell_inline_command(command: str, shell: str | None = None) -> list[str]:
    """Build a command list for running a shell inline command."""
    sh = shell or _resolve_shell()
    return [sh, "-c", command]


# ─── stable-node-path.ts ───

def resolve_stable_node_path() -> str | None:
    """Resolve a stable node binary path."""
    import shutil
    # Prefer explicit env var
    explicit = os.environ.get("OPENCLAW_NODE_PATH", "").strip()
    if explicit and os.path.isfile(explicit) and os.access(explicit, os.X_OK):
        return explicit

    # Try common paths
    candidates = [
        "/usr/local/bin/node",
        "/usr/bin/node",
        os.path.expanduser("~/.nvm/versions/node/*/bin/node"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return shutil.which("node")


# ─── node-shell.ts / node-commands.ts ───

def get_node_shell() -> str:
    """Get the shell to use for node child processes."""
    return os.environ.get("OPENCLAW_NODE_SHELL", DEFAULT_SHELL)


def build_node_command(script: str, args: list[str] | None = None) -> list[str]:
    """Build a node command list."""
    node = resolve_stable_node_path() or "node"
    cmd = [node, script]
    if args:
        cmd.extend(args)
    return cmd

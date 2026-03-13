"""Environment variable handling for configuration.

Ported from bk/src/config/env-vars.ts (88 lines), env-substitution.ts (203 lines),
env-preserve.ts, allowed-values.ts, prototype-keys.ts.

Handles env var application from config.env, ${VAR} substitution in config values,
env var reference preservation for write-back, and prototype key blocking.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Pattern for ${VAR} and ${VAR:-default} references
ENV_VAR_PATTERN = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-((?:[^}]|\\\})*))?\}"
)


class MissingEnvVarError(Exception):
    """Raised when a required env var is missing."""
    def __init__(self, var_name: str, config_path: str = ""):
        self.var_name = var_name
        self.config_path = config_path
        super().__init__(f"Missing env var: {var_name} (at {config_path})")


# ─── env-vars.ts — Apply config.env to process env ───

def apply_config_env_vars(
    cfg: dict[str, Any],
    env: dict[str, str] | None = None,
) -> None:
    """Apply config.env.vars entries to the environment.

    Only sets vars that are not already set in the environment.
    """
    target = env if env is not None else os.environ
    env_section = cfg.get("env", {}) or {}
    vars_section = env_section.get("vars", {}) or {}

    if not isinstance(vars_section, dict):
        return

    for key, value in vars_section.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if key in target:
            continue  # Don't override existing
        if isinstance(value, str):
            target[key] = value
        elif isinstance(value, (int, float, bool)):
            target[key] = str(value)


# ─── env-substitution.ts — ${VAR} substitution ───

def contains_env_var_reference(value: str) -> bool:
    """Check if a string contains any ${VAR} references."""
    return bool(ENV_VAR_PATTERN.search(value))


def substitute_env_vars(
    value: str,
    env: dict[str, str] | None = None,
    *,
    on_missing: Callable[[dict[str, str]], None] | None = None,
) -> str:
    """Substitute ${VAR} and ${VAR:-default} references in a string."""
    e = env or os.environ

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        default_value = match.group(2)
        resolved = e.get(var_name)
        if resolved is not None:
            return resolved
        if default_value is not None:
            return default_value.replace(r"\}", "}")
        if on_missing:
            on_missing({"varName": var_name, "configPath": ""})
        return match.group(0)  # Keep original if unresolved

    return ENV_VAR_PATTERN.sub(_replace, value)


def resolve_config_env_vars(
    value: Any,
    env: dict[str, str] | None = None,
    *,
    on_missing: Callable[[dict[str, str]], None] | None = None,
    _path: str = "",
) -> Any:
    """Recursively substitute ${VAR} refs in a config structure."""
    if isinstance(value, str):
        if not contains_env_var_reference(value):
            return value
        return substitute_env_vars(
            value, env,
            on_missing=lambda w: on_missing({**w, "configPath": _path}) if on_missing else None,
        )
    if isinstance(value, list):
        return [
            resolve_config_env_vars(
                item, env, on_missing=on_missing,
                _path=f"{_path}[{i}]",
            )
            for i, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            k: resolve_config_env_vars(
                v, env, on_missing=on_missing,
                _path=f"{_path}.{k}" if _path else k,
            )
            for k, v in value.items()
        }
    return value


# ─── env-preserve.ts — Restore env var refs for write-back ───

def collect_env_ref_paths(
    value: Any,
    path: str = "",
    output: dict[str, str] | None = None,
) -> dict[str, str]:
    """Collect all paths containing ${VAR} references."""
    result = output if output is not None else {}
    if isinstance(value, str):
        if contains_env_var_reference(value):
            result[path] = value
        return result
    if isinstance(value, list):
        for i, item in enumerate(value):
            collect_env_ref_paths(item, f"{path}[{i}]", result)
        return result
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            collect_env_ref_paths(child, child_path, result)
        return result
    return result


def restore_env_var_refs(
    value: Any,
    env_ref_map: dict[str, str],
    changed_paths: set[str] | None = None,
    *,
    _path: str = "",
) -> Any:
    """Restore ${VAR} references in paths that weren't changed."""
    changes = changed_paths or set()
    if isinstance(value, str):
        if not _is_path_changed(_path, changes):
            original = env_ref_map.get(_path)
            if original is not None:
                return original
        return value
    if isinstance(value, list):
        changed = False
        result = []
        for i, item in enumerate(value):
            updated = restore_env_var_refs(
                item, env_ref_map, changes,
                _path=f"{_path}[{i}]",
            )
            if updated is not item:
                changed = True
            result.append(updated)
        return result if changed else value
    if isinstance(value, dict):
        changed = False
        result_dict: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{_path}.{key}" if _path else key
            updated = restore_env_var_refs(
                child, env_ref_map, changes,
                _path=child_path,
            )
            if updated is not child:
                changed = True
            result_dict[key] = updated
        return result_dict if changed else value
    return value


def _parent_path(path: str) -> str:
    """Get the parent path."""
    if not path:
        return ""
    if path.endswith("]"):
        idx = path.rfind("[")
        return path[:idx] if idx > 0 else ""
    idx = path.rfind(".")
    return path[:idx] if idx >= 0 else ""


def _is_path_changed(path: str, changed_paths: set[str]) -> bool:
    """Check if a path or any ancestor was changed."""
    if path in changed_paths:
        return True
    current = _parent_path(path)
    while current:
        if current in changed_paths:
            return True
        current = _parent_path(current)
    return "" in changed_paths


# ─── prototype-keys.ts — Prototype key blocking ───

BLOCKED_OBJECT_KEYS = frozenset({
    "__proto__",
    "constructor",
    "prototype",
    "__defineGetter__",
    "__defineSetter__",
    "__lookupGetter__",
    "__lookupSetter__",
})


def is_blocked_object_key(key: str) -> bool:
    """Check if a key is a blocked prototype key."""
    return key in BLOCKED_OBJECT_KEYS

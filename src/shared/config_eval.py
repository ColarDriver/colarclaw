"""Shared config evaluation — ported from bk/src/shared/config-eval.ts.

Config path resolution, truthiness checks, binary discovery,
and runtime requirements evaluation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable


# ─── truthiness ───

def is_truthy(value: Any) -> bool:
    """Check if a value is truthy (matching TS semantics)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return len(value.strip()) > 0
    return True


# ─── config path ───

def resolve_config_path(config: Any, path_str: str) -> Any:
    """Resolve a dotted path in a nested config dict."""
    parts = [p for p in path_str.split(".") if p]
    current = config
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def is_config_path_truthy_with_defaults(
    config: Any,
    path_str: str,
    defaults: dict[str, bool],
) -> bool:
    value = resolve_config_path(config, path_str)
    if value is None and path_str in defaults:
        return defaults.get(path_str, False)
    return is_truthy(value)


# ─── binary detection ───

_binary_cache: dict[str, bool] = {}
_cached_path: str = ""


def has_binary(bin_name: str) -> bool:
    """Check if a binary exists on PATH (cached)."""
    global _binary_cache, _cached_path
    path_env = os.environ.get("PATH", "")
    if path_env != _cached_path:
        _cached_path = path_env
        _binary_cache.clear()

    if bin_name in _binary_cache:
        return _binary_cache[bin_name]

    dirs = path_env.split(os.pathsep)
    for d in dirs:
        candidate = Path(d) / bin_name
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            _binary_cache[bin_name] = True
            return True

    _binary_cache[bin_name] = False
    return False


# ─── runtime requirements ───

def evaluate_runtime_requires(
    requires: dict[str, Any] | None = None,
    has_bin: Callable[[str], bool] = has_binary,
    has_env: Callable[[str], bool] | None = None,
    is_config_path_truthy: Callable[[str], bool] | None = None,
    has_remote_bin: Callable[[str], bool] | None = None,
    has_any_remote_bin: Callable[[list[str]], bool] | None = None,
) -> bool:
    """Evaluate runtime requirements."""
    if not requires:
        return True

    def _has_env(name: str) -> bool:
        if has_env:
            return has_env(name)
        return bool(os.environ.get(name, "").strip())

    def _config_truthy(path: str) -> bool:
        if is_config_path_truthy:
            return is_config_path_truthy(path)
        return False

    # Required bins
    for bin_name in requires.get("bins", []):
        if has_bin(bin_name):
            continue
        if has_remote_bin and has_remote_bin(bin_name):
            continue
        return False

    # Any bins
    any_bins = requires.get("anyBins", [])
    if any_bins:
        any_found = any(has_bin(b) for b in any_bins)
        if not any_found and not (has_any_remote_bin and has_any_remote_bin(any_bins)):
            return False

    # Required env
    for env_name in requires.get("env", []):
        if not _has_env(env_name):
            return False

    # Required config
    for config_path in requires.get("config", []):
        if not _config_truthy(config_path):
            return False

    return True


def resolve_runtime_platform() -> str:
    """Resolve the current runtime platform."""
    return sys.platform


def evaluate_runtime_eligibility(
    requires: dict[str, Any] | None = None,
    os_list: list[str] | None = None,
    remote_platforms: list[str] | None = None,
    always: bool = False,
    **kwargs: Any,
) -> bool:
    """Evaluate runtime eligibility including OS checks."""
    os_req = os_list or []
    remotes = remote_platforms or []
    if os_req:
        platform = resolve_runtime_platform()
        if platform not in os_req and not any(p in os_req for p in remotes):
            return False
    if always:
        return True
    return evaluate_runtime_requires(requires, **kwargs)

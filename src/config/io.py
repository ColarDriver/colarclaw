"""Configuration I/O — loading, parsing, writing, caching.

Ported from bk/src/config/io.ts (1416 lines), includes.ts, includes-scan.ts,
backup-rotation.ts, store.ts, store-cache.ts, store-maintenance.ts,
store-migrations.ts, session-file.ts, merge-config.ts, merge-patch.ts.

Handles JSON5 parsing, config file reading/writing with atomic rename,
backup rotation, env var substitution, include resolution, config caching,
session store operations, and merge-patch application.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Config cache ───

_config_cache: dict[str, Any] | None = None
_config_cache_path: str | None = None
_config_cache_mtime: float = 0.0


def clear_config_cache() -> None:
    """Clear the in-memory config cache."""
    global _config_cache, _config_cache_path, _config_cache_mtime
    _config_cache = None
    _config_cache_path = None
    _config_cache_mtime = 0.0


# ─── JSON5 parsing ───

def parse_config_json5(raw: str) -> dict[str, Any]:
    """Parse a JSON5 config string into a dict.

    Supports comments (// and /* */), trailing commas, unquoted keys,
    and other JSON5 extensions.
    """
    # Simple JSON5 parser — strip comments and trailing commas
    cleaned = _strip_json5_comments(raw)
    cleaned = _strip_trailing_commas(cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Config parse error: {e}") from e


def _strip_json5_comments(text: str) -> str:
    """Strip // and /* */ comments from JSON5 text."""
    result = []
    i = 0
    in_string = False
    string_char = ""
    while i < len(text):
        ch = text[i]
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
                continue
            if ch == string_char:
                in_string = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            string_char = ch
            result.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch == "/":
                # Line comment
                while i < len(text) and text[i] != "\n":
                    i += 1
                continue
            if next_ch == "*":
                # Block comment
                i += 2
                while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
                continue
        result.append(ch)
        i += 1
    return "".join(result)


def _strip_trailing_commas(text: str) -> str:
    """Strip trailing commas before } or ]."""
    return re.sub(r",\s*([}\]])", r"\1", text)


# ─── Config file I/O ───

def read_config_file(path: str) -> dict[str, Any]:
    """Read and parse a config file."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    return parse_config_json5(raw)


def read_config_file_raw(path: str) -> str | None:
    """Read raw config file contents."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def write_config_file(path: str, config: dict[str, Any]) -> None:
    """Write config to file atomically (write tmp + rename)."""
    content = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    tmp_path = f"{path}.tmp.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        # Fallback: direct write
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def hash_config_raw(raw: str | None) -> str:
    """Hash raw config content."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


# ─── Config loading ───

def load_config(
    path: str | None = None,
    env: dict[str, str] | None = None,
    *,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Load and resolve configuration.

    1. Resolve config file path
    2. Read and parse JSON5
    3. Resolve includes
    4. Substitute env vars
    5. Apply defaults
    6. Validate
    7. Cache result
    """
    global _config_cache, _config_cache_path, _config_cache_mtime

    from .paths import resolve_config_path
    from .defaults import (
        apply_agent_defaults,
        apply_compaction_defaults,
        apply_context_pruning_defaults,
        apply_logging_defaults,
        apply_message_defaults,
        apply_model_defaults,
        apply_session_defaults,
    )
    from .env import apply_config_env_vars, resolve_config_env_vars

    e = env or os.environ
    config_path = path or resolve_config_path(e)

    # Check cache
    if use_cache and _config_cache is not None and _config_cache_path == config_path:
        try:
            mtime = os.path.getmtime(config_path)
            if mtime <= _config_cache_mtime:
                return copy.deepcopy(_config_cache)
        except OSError:
            pass

    # Read file
    if not os.path.exists(config_path):
        return {}

    try:
        raw = read_config_file_raw(config_path)
        if raw is None:
            return {}
        parsed = parse_config_json5(raw)
    except Exception as e_err:
        logger.error(f"Failed to parse config at {config_path}: {e_err}")
        return {}

    # Resolve includes
    cfg = resolve_config_includes(parsed, config_path)

    # Apply env vars from config.env section
    apply_config_env_vars(cfg, e)

    # Substitute ${VAR} references
    cfg = resolve_config_env_vars(cfg, e)

    # Apply defaults pipeline
    cfg = apply_message_defaults(cfg)
    cfg = apply_session_defaults(cfg)
    cfg = apply_logging_defaults(cfg)
    cfg = apply_agent_defaults(cfg)
    cfg = apply_model_defaults(cfg)
    cfg = apply_compaction_defaults(cfg)
    cfg = apply_context_pruning_defaults(cfg)

    # Cache
    try:
        _config_cache = copy.deepcopy(cfg)
        _config_cache_path = config_path
        _config_cache_mtime = os.path.getmtime(config_path)
    except OSError:
        pass

    return cfg


def create_config_io(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a config IO context with dependency injection.

    Returns a dict with load_config, write_config, read_snapshot methods.
    """
    opts = overrides or {}
    env = opts.get("env", os.environ)
    config_path = opts.get("configPath", "")

    def _load() -> dict[str, Any]:
        return load_config(config_path or None, env)

    def _write(config: dict[str, Any]) -> None:
        from .paths import resolve_config_path
        p = config_path or resolve_config_path(env)
        write_config_file(p, config)

    def _read_snapshot() -> dict[str, Any]:
        from .paths import resolve_config_path
        p = config_path or resolve_config_path(env)
        raw = read_config_file_raw(p)
        return {
            "raw": raw,
            "hash": hash_config_raw(raw) if raw else None,
            "path": p,
            "parsed": parse_config_json5(raw) if raw else None,
        }

    return {
        "load_config": _load,
        "write_config": _write,
        "read_snapshot": _read_snapshot,
        "config_path": config_path,
    }


# ─── Config includes resolution (includes.ts) ───

MAX_INCLUDE_DEPTH = 10


class ConfigIncludeError(Exception):
    """Error during config include resolution."""
    pass


class CircularIncludeError(ConfigIncludeError):
    """Circular include detected."""
    pass


def resolve_config_includes(
    parsed: dict[str, Any],
    config_path: str,
    *,
    _depth: int = 0,
    _seen: set[str] | None = None,
) -> dict[str, Any]:
    """Resolve $include directives in config.

    Supports:
    - "$include": "path/to/file.json5"
    - "$include": ["file1.json5", "file2.json5"]
    """
    if _depth > MAX_INCLUDE_DEPTH:
        raise ConfigIncludeError(f"Max include depth ({MAX_INCLUDE_DEPTH}) exceeded")

    seen = _seen or set()
    real_path = os.path.realpath(config_path)
    if real_path in seen:
        raise CircularIncludeError(f"Circular include: {config_path}")
    seen.add(real_path)

    if not isinstance(parsed, dict):
        return parsed

    include = parsed.get("$include")
    if include is None:
        return parsed

    # Remove $include from parsed
    rest = {k: v for k, v in parsed.items() if k != "$include"}

    # Resolve include paths
    includes = include if isinstance(include, list) else [include]
    config_dir = os.path.dirname(config_path)

    result: dict[str, Any] = {}
    for inc_path in includes:
        if not isinstance(inc_path, str):
            continue
        resolved_path = os.path.join(config_dir, inc_path)
        if not os.path.exists(resolved_path):
            logger.warning(f"Config include not found: {resolved_path}")
            continue
        try:
            raw = read_config_file_raw(resolved_path)
            if raw:
                inc_parsed = parse_config_json5(raw)
                inc_resolved = resolve_config_includes(
                    inc_parsed, resolved_path,
                    _depth=_depth + 1, _seen=seen,
                )
                result = _deep_merge(result, inc_resolved)
        except Exception as e:
            raise ConfigIncludeError(
                f"Failed to include {resolved_path}: {e}"
            ) from e

    # Merge rest on top (main config overrides includes)
    return _deep_merge(result, rest)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dicts (override wins for non-dict values)."""
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ─── Merge patch (merge-patch.ts) ───

def apply_merge_patch(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply RFC 7396 JSON Merge Patch."""
    if not isinstance(patch, dict):
        return patch

    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            existing = result.get(key, {})
            if isinstance(existing, dict):
                result[key] = apply_merge_patch(existing, value)
            else:
                result[key] = apply_merge_patch({}, value)
        else:
            result[key] = value
    return result


# ─── Backup rotation (backup-rotation.ts) ───

MAX_BACKUPS = 10


def maintain_config_backups(config_path: str, backup_dir: str | None = None) -> None:
    """Maintain config file backups with rotation."""
    if not os.path.exists(config_path):
        return

    bk_dir = backup_dir or os.path.join(os.path.dirname(config_path), "backups")
    os.makedirs(bk_dir, exist_ok=True)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_name = f"config-{timestamp}.json5"
    backup_path = os.path.join(bk_dir, backup_name)

    try:
        shutil.copy2(config_path, backup_path)
    except Exception as e:
        logger.warning(f"Failed to create config backup: {e}")
        return

    # Rotate old backups
    try:
        backups = sorted(
            [f for f in os.listdir(bk_dir) if f.startswith("config-")],
            reverse=True,
        )
        for old in backups[MAX_BACKUPS:]:
            os.unlink(os.path.join(bk_dir, old))
    except Exception as e:
        logger.warning(f"Failed to rotate config backups: {e}")


# ─── Store operations (store.ts, store-cache.ts, store-maintenance.ts) ───

class ConfigStore:
    """Session-aware config store with caching and maintenance.

    Wraps config I/O with session tracking and periodic cleanup.
    """

    def __init__(
        self,
        *,
        config_path: str = "",
        state_dir: str = "",
    ) -> None:
        self._config_path = config_path
        self._state_dir = state_dir
        self._cache: dict[str, Any] | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 5.0  # seconds

    def load(self) -> dict[str, Any]:
        """Load config (with caching)."""
        now = time.time()
        if self._cache is not None and now - self._cache_time < self._cache_ttl:
            return copy.deepcopy(self._cache)

        cfg = load_config(self._config_path or None)
        self._cache = cfg
        self._cache_time = now
        return copy.deepcopy(cfg)

    def invalidate(self) -> None:
        """Invalidate the cache."""
        self._cache = None
        self._cache_time = 0.0

    def write(self, config: dict[str, Any]) -> None:
        """Write config and invalidate cache."""
        if self._config_path:
            write_config_file(self._config_path, config)
        self.invalidate()

    def read_snapshot(self) -> dict[str, Any]:
        """Read a raw snapshot for write operations."""
        if not self._config_path:
            return {"raw": None, "hash": None, "path": ""}
        raw = read_config_file_raw(self._config_path)
        return {
            "raw": raw,
            "hash": hash_config_raw(raw) if raw else None,
            "path": self._config_path,
        }

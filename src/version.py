"""Version — resolve OpenClaw version at runtime.

Ported from bk/src/version.ts (128行).
"""
from __future__ import annotations

import json
import os
from typing import Any

__all__ = ["get_version", "get_build_info", "get_full_version_string"]

_cached_version: str | None = None
_cached_build_info: dict[str, Any] | None = None


def get_version() -> str:
    """Get the current OpenClaw version."""
    global _cached_version
    if _cached_version:
        return _cached_version

    # Try __version__ from root package
    try:
        from . import __version__
        if __version__:
            _cached_version = __version__
            return __version__
    except (ImportError, AttributeError):
        pass

    # Try reading from package.json
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "package.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "package.json"),
    ]
    for path in candidates:
        try:
            with open(os.path.abspath(path)) as f:
                data = json.load(f)
                version = data.get("version", "")
                if version:
                    _cached_version = version
                    return version
        except Exception:
            continue

    # Try pyproject.toml
    try:
        toml_path = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        with open(os.path.abspath(toml_path)) as f:
            for line in f:
                if line.strip().startswith("version"):
                    version = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if version:
                        _cached_version = version
                        return version
    except Exception:
        pass

    _cached_version = "0.0.0-dev"
    return _cached_version


def get_build_info() -> dict[str, Any]:
    """Get build info (commit, date, etc)."""
    global _cached_build_info
    if _cached_build_info is not None:
        return _cached_build_info

    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "build-info.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "build-info.json"),
    ]
    for path in candidates:
        try:
            with open(os.path.abspath(path)) as f:
                _cached_build_info = json.load(f)
                return _cached_build_info
        except Exception:
            continue

    _cached_build_info = {}
    return _cached_build_info


def get_full_version_string() -> str:
    """Get full version string with build info."""
    version = get_version()
    build = get_build_info()
    commit = build.get("commit", "")[:8]
    if commit:
        return f"{version} ({commit})"
    return version

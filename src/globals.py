"""Globals — runtime global constants and environment detection.

Ported from bk/src/globals.ts (52行) + bk/src/runtime.ts (53行).
"""
from __future__ import annotations

import os
import sys
import platform

__all__ = [
    "IS_DEV", "IS_TEST", "IS_PRODUCTION",
    "IS_DOCKER", "IS_CI", "IS_TTY",
    "IS_MACOS", "IS_LINUX", "IS_WINDOWS",
    "DATA_DIR", "CONFIG_DIR", "CACHE_DIR",
    "PACKAGE_NAME",
]

# ─── Environment detection ───

PACKAGE_NAME = "colarcore"

IS_DEV = os.environ.get("NODE_ENV") == "development" or os.environ.get("COLARCORE_DEV") == "1"
IS_TEST = "pytest" in sys.modules or os.environ.get("COLARCORE_TEST") == "1"
IS_PRODUCTION = not IS_DEV and not IS_TEST
IS_DOCKER = os.path.exists("/.dockerenv") or os.environ.get("DOCKER") == "1"
IS_CI = bool(os.environ.get("CI")) or bool(os.environ.get("GITHUB_ACTIONS"))
IS_TTY = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

# ─── Platform detection ───

_system = platform.system()
IS_MACOS = _system == "Darwin"
IS_LINUX = _system == "Linux"
IS_WINDOWS = _system == "Windows"

# ─── Standard directories ───

if IS_MACOS:
    DATA_DIR = os.path.expanduser("~/Library/Application Support/colarcore")
    CONFIG_DIR = os.path.expanduser("~/.colarcore")
    CACHE_DIR = os.path.expanduser("~/Library/Caches/colarcore")
elif IS_WINDOWS:
    DATA_DIR = os.path.join(os.environ.get("APPDATA", ""), "colarcore")
    CONFIG_DIR = DATA_DIR
    CACHE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "colarcore", "cache")
else:  # Linux / other
    DATA_DIR = os.path.expanduser(os.environ.get("XDG_DATA_HOME", "~/.local/share") + "/colarcore")
    CONFIG_DIR = os.path.expanduser(os.environ.get("XDG_CONFIG_HOME", "~/.config") + "/colarcore")
    CACHE_DIR = os.path.expanduser(os.environ.get("XDG_CACHE_HOME", "~/.cache") + "/colarcore")

# Override from env
DATA_DIR = os.environ.get("COLARCORE_DATA_DIR", DATA_DIR)
CONFIG_DIR = os.environ.get("COLARCORE_CONFIG_DIR", CONFIG_DIR)
CACHE_DIR = os.environ.get("COLARCORE_CACHE_DIR", CACHE_DIR)

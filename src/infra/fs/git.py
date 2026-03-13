"""Infra git — ported from bk/src/infra/git-root.ts, git-commit.ts,
brew.ts, home-dir.ts, executable-path.ts, package-tag.ts.

Git root discovery, commit hash resolution, Homebrew/Linuxbrew path
resolution, home directory resolution, executable path search.
"""
from __future__ import annotations

import json
import logging
import os
import re
import stat
from pathlib import Path
from typing import Any

logger = logging.getLogger("infra.git")

DEFAULT_GIT_DISCOVERY_MAX_DEPTH = 12


# ─── git-root.ts ───

def _walk_up_from(start_dir: str, max_depth: int, check):
    """Walk up from start_dir calling check(dir); returns first non-None."""
    current = os.path.abspath(start_dir)
    for _ in range(max_depth):
        result = check(current)
        if result is not None:
            return result
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def _has_git_marker(repo_root: str) -> bool:
    git_path = os.path.join(repo_root, ".git")
    try:
        st = os.stat(git_path)
        return stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)
    except OSError:
        return False


def find_git_root(start_dir: str, max_depth: int = DEFAULT_GIT_DISCOVERY_MAX_DEPTH) -> str | None:
    """Find the nearest git repository root."""
    return _walk_up_from(start_dir, max_depth,
                         lambda d: d if _has_git_marker(d) else None)


def _resolve_git_dir_from_marker(repo_root: str) -> str | None:
    git_path = os.path.join(repo_root, ".git")
    try:
        st = os.stat(git_path)
        if stat.S_ISDIR(st.st_mode):
            return git_path
        if not stat.S_ISREG(st.st_mode):
            return None
        with open(git_path, "r") as f:
            raw = f.read()
        match = re.search(r"gitdir:\s*(.+)", raw, re.I)
        if not match or not match.group(1):
            return None
        return os.path.abspath(os.path.join(repo_root, match.group(1).strip()))
    except OSError:
        return None


def resolve_git_head_path(start_dir: str, max_depth: int = DEFAULT_GIT_DISCOVERY_MAX_DEPTH) -> str | None:
    def check(repo_root):
        git_dir = _resolve_git_dir_from_marker(repo_root)
        return os.path.join(git_dir, "HEAD") if git_dir else None
    return _walk_up_from(start_dir, max_depth, check)


# ─── git-commit.ts ───

_commit_cache: dict[str, str | None] = {}


def _format_commit(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    match = re.search(r"[0-9a-fA-F]{7,40}", trimmed)
    if not match:
        return None
    return match.group(0)[:7].lower()


def _safe_read_file_prefix(file_path: str, limit: int = 256) -> str:
    try:
        with open(file_path, "r") as f:
            return f.read(limit)
    except OSError:
        return ""


def _resolve_git_refs_base(head_path: str) -> str:
    git_dir = os.path.dirname(head_path)
    try:
        common = _safe_read_file_prefix(os.path.join(git_dir, "commondir")).strip()
        if common:
            return os.path.abspath(os.path.join(git_dir, common))
    except OSError:
        pass
    return git_dir


def _resolve_ref_path(head_path: str, ref: str) -> str | None:
    if not ref.startswith("refs/"):
        return None
    if os.path.isabs(ref):
        return None
    if ".." in ref.split("/"):
        return None
    refs_base = _resolve_git_refs_base(head_path)
    resolved = os.path.abspath(os.path.join(refs_base, ref))
    rel = os.path.relpath(resolved, refs_base)
    if not rel or rel.startswith("..") or os.path.isabs(rel):
        return None
    return resolved


def _read_commit_from_git(search_dir: str) -> str | None:
    head_path = resolve_git_head_path(search_dir)
    if not head_path:
        return None
    try:
        with open(head_path, "r") as f:
            head = f.read().strip()
    except OSError:
        return None
    if not head:
        return None
    if head.startswith("ref:"):
        ref = re.sub(r"^ref:\s*", "", head, flags=re.I).strip()
        ref_path = _resolve_ref_path(head_path, ref)
        if not ref_path:
            return None
        return _format_commit(_safe_read_file_prefix(ref_path).strip())
    return _format_commit(head)


def resolve_commit_hash(
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> str | None:
    """Resolve the current git commit hash."""
    e = env or os.environ
    env_commit = (e.get("GIT_COMMIT") or e.get("GIT_SHA") or "").strip()
    normalized = _format_commit(env_commit)
    if normalized:
        return normalized

    search_dir = os.path.abspath(cwd or os.getcwd())
    if search_dir in _commit_cache:
        return _commit_cache[search_dir]

    try:
        commit = _read_commit_from_git(search_dir)
        _commit_cache[search_dir] = commit
        return commit
    except OSError:
        _commit_cache[search_dir] = None
        return None


# ─── brew.ts ───

def resolve_brew_path_dirs(
    home_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Resolve Homebrew/Linuxbrew PATH directories."""
    home = home_dir or str(Path.home())
    e = env or os.environ
    dirs: list[str] = []

    prefix = e.get("HOMEBREW_PREFIX", "").strip()
    if prefix:
        dirs.extend([os.path.join(prefix, "bin"), os.path.join(prefix, "sbin")])

    dirs.extend([
        os.path.join(home, ".linuxbrew", "bin"),
        os.path.join(home, ".linuxbrew", "sbin"),
        "/home/linuxbrew/.linuxbrew/bin",
        "/home/linuxbrew/.linuxbrew/sbin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ])
    return dirs


def resolve_brew_executable(
    home_dir: str | None = None,
    env: dict[str, str] | None = None,
) -> str | None:
    """Find the brew executable."""
    home = home_dir or str(Path.home())
    e = env or os.environ
    candidates: list[str] = []

    brew_file = e.get("HOMEBREW_BREW_FILE", "").strip()
    if brew_file:
        candidates.append(brew_file)

    prefix = e.get("HOMEBREW_PREFIX", "").strip()
    if prefix:
        candidates.append(os.path.join(prefix, "bin", "brew"))

    candidates.extend([
        os.path.join(home, ".linuxbrew", "bin", "brew"),
        "/home/linuxbrew/.linuxbrew/bin/brew",
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
    ])

    for c in candidates:
        if os.access(c, os.X_OK):
            return c
    return None


# ─── home-dir.ts ───

def resolve_effective_home_dir(env: dict[str, str] | None = None) -> str | None:
    """Resolve the effective home directory."""
    e = env or os.environ
    explicit = e.get("OPENCLAW_HOME", "").strip()
    if explicit:
        if explicit == "~" or explicit.startswith("~/") or explicit.startswith("~\\"):
            fallback = e.get("HOME") or e.get("USERPROFILE") or str(Path.home())
            return os.path.abspath(explicit.replace("~", fallback, 1))
        return os.path.abspath(explicit)

    for key in ("HOME", "USERPROFILE"):
        val = e.get(key, "").strip()
        if val:
            return os.path.abspath(val)

    try:
        return str(Path.home())
    except (RuntimeError, KeyError):
        return None


def resolve_required_home_dir(env: dict[str, str] | None = None) -> str:
    return resolve_effective_home_dir(env) or os.path.abspath(os.getcwd())


def expand_home_prefix(input_str: str, home: str | None = None) -> str:
    """Expand ~ prefix in a path."""
    if not input_str.startswith("~"):
        return input_str
    h = home or resolve_effective_home_dir()
    if not h:
        return input_str
    return input_str.replace("~", h, 1) if input_str == "~" or input_str[1:2] in ("/", "\\") else input_str


# ─── executable-path.ts ───

def find_executable(name: str, search_dirs: list[str] | None = None) -> str | None:
    """Find executable in search dirs or PATH."""
    import shutil
    if search_dirs:
        for d in search_dirs:
            candidate = os.path.join(d, name)
            if os.access(candidate, os.X_OK):
                return candidate
    return shutil.which(name)


# ─── package-tag.ts ───

def resolve_package_tag(version: str) -> str:
    """Resolve npm dist-tag from a version string."""
    if "-beta" in version:
        return "beta"
    if "-alpha" in version:
        return "alpha"
    if "-" in version:
        return "next"
    return "latest"

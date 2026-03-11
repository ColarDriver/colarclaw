"""Sandbox path resolution — ported from bk/src/agents/sandbox-paths.ts.

Handles path resolution, boundary checks, and media source resolution
for sandboxed execution environments.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

UNICODE_SPACES = re.compile(r"[\u00A0\u2000-\u200A\u202F\u205F\u3000]")
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
DATA_URL_RE = re.compile(r"^data:", re.IGNORECASE)
SANDBOX_CONTAINER_WORKDIR = "/workspace"


def _normalize_unicode_spaces(s: str) -> str:
    return UNICODE_SPACES.sub(" ", s)


def _normalize_at_prefix(file_path: str) -> str:
    return file_path[1:] if file_path.startswith("@") else file_path


def _expand_path(file_path: str) -> str:
    normalized = _normalize_unicode_spaces(_normalize_at_prefix(file_path))
    if normalized == "~":
        return os.path.expanduser("~")
    if normalized.startswith("~/"):
        return os.path.expanduser(normalized)
    return normalized


def _resolve_to_cwd(file_path: str, cwd: str) -> str:
    expanded = _expand_path(file_path)
    if os.path.isabs(expanded):
        return expanded
    return os.path.normpath(os.path.join(cwd, expanded))


def _short_path(value: str) -> str:
    home = os.path.expanduser("~")
    if value.startswith(home):
        return "~" + value[len(home):]
    return value


def _is_path_inside(root: str, path_to_check: str) -> bool:
    """Check if path_to_check is inside root."""
    root_real = os.path.realpath(root)
    path_real = os.path.realpath(path_to_check)
    return path_real.startswith(root_real + os.sep) or path_real == root_real


# ── Public API ─────────────────────────────────────────────────────────────

def resolve_sandbox_input_path(file_path: str, cwd: str) -> str:
    """Resolve a file path within the sandbox context."""
    return _resolve_to_cwd(file_path, cwd)


@dataclass(frozen=True)
class SandboxPathResult:
    resolved: str
    relative: str


def resolve_sandbox_path(file_path: str, cwd: str, root: str) -> SandboxPathResult:
    """Resolve a path within sandbox boundaries."""
    resolved = resolve_sandbox_input_path(file_path, cwd)
    root_resolved = os.path.normpath(root)
    relative = os.path.relpath(resolved, root_resolved)
    if not relative:
        return SandboxPathResult(resolved=resolved, relative="")
    if relative.startswith("..") or os.path.isabs(relative):
        raise ValueError(
            f"Path escapes sandbox root ({_short_path(root_resolved)}): {file_path}"
        )
    return SandboxPathResult(resolved=resolved, relative=relative)


def assert_media_not_data_url(media: str) -> None:
    """Raise an error if media is a data: URL."""
    raw = media.strip()
    if DATA_URL_RE.match(raw):
        raise ValueError("data: URLs are not supported for media. Use buffer instead.")


def _map_container_workspace_path(
    candidate: str,
    sandbox_root: str,
) -> str | None:
    """Map a container /workspace path to the actual sandbox root path."""
    normalized = candidate.replace("\\", "/")
    if normalized == SANDBOX_CONTAINER_WORKDIR:
        return os.path.normpath(sandbox_root)
    prefix = f"{SANDBOX_CONTAINER_WORKDIR}/"
    if not normalized.startswith(prefix):
        return None
    rel = normalized[len(prefix):]
    if not rel:
        return os.path.normpath(sandbox_root)
    parts = [p for p in rel.split("/") if p]
    return os.path.normpath(os.path.join(sandbox_root, *parts))


def resolve_sandboxed_media_source(media: str, sandbox_root: str) -> str:
    """Resolve a media source path for sandboxed execution."""
    raw = media.strip()
    if not raw:
        return raw
    if HTTP_URL_RE.match(raw):
        return raw

    candidate = raw

    # Map file:// URLs
    if raw.lower().startswith("file://"):
        from urllib.parse import urlparse, unquote
        parsed = urlparse(raw)
        pathname = unquote(parsed.path).replace("\\", "/")
        mapped = _map_container_workspace_path(pathname, sandbox_root)
        if mapped:
            candidate = mapped
        else:
            # Convert file:// URL to local path
            if os.name == "nt":
                candidate = pathname.lstrip("/")
            else:
                candidate = pathname

    # Map container workspace paths
    container_mapped = _map_container_workspace_path(candidate, sandbox_root)
    if container_mapped:
        candidate = container_mapped

    # Resolve within sandbox
    result = resolve_sandbox_path(candidate, sandbox_root, sandbox_root)
    return result.resolved


# ── Sandbox configuration types ───────────────────────────────────────────

DEFAULT_SANDBOX_IMAGE = "openclaw/sandbox:latest"
DEFAULT_SANDBOX_COMMON_IMAGE = "openclaw/sandbox-common:latest"
DEFAULT_SANDBOX_BROWSER_IMAGE = "openclaw/sandbox-browser:latest"


@dataclass
class SandboxConfig:
    scope: str = "session"  # "session" | "agent" | "global"
    image: str = DEFAULT_SANDBOX_IMAGE
    enabled: bool = False


@dataclass
class SandboxDockerConfig:
    image: str = DEFAULT_SANDBOX_IMAGE
    common_image: str = DEFAULT_SANDBOX_COMMON_IMAGE
    network: str = "bridge"


@dataclass
class SandboxBrowserConfig:
    image: str = DEFAULT_SANDBOX_BROWSER_IMAGE
    enabled: bool = False


@dataclass
class SandboxContext:
    root: str
    cwd: str
    workspace_dir: str


def resolve_sandbox_scope(config: dict | None = None) -> str:
    """Resolve sandbox scope from config."""
    if config and isinstance(config, dict):
        scope = config.get("sandbox", {}).get("scope", "session")
        if scope in ("session", "agent", "global"):
            return scope
    return "session"

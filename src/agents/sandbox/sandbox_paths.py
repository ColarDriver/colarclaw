"""Sandbox paths — ported from bk/src/agents/sandbox-paths.ts.

Path resolution, sandboxed path validation, and workspace path mapping.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

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
    home = str(Path.home())
    if normalized == "~":
        return home
    if normalized.startswith("~/"):
        return home + normalized[1:]
    return normalized


def resolve_sandbox_input_path(file_path: str, cwd: str) -> str:
    expanded = _expand_path(file_path)
    if os.path.isabs(expanded):
        return expanded
    return os.path.normpath(os.path.join(cwd, expanded))


def resolve_sandbox_path(file_path: str, cwd: str, root: str) -> dict[str, str]:
    resolved = resolve_sandbox_input_path(file_path, cwd)
    root_resolved = os.path.normpath(os.path.abspath(root))
    relative = os.path.relpath(resolved, root_resolved)
    if relative.startswith("..") or os.path.isabs(relative):
        raise ValueError(f"Path escapes sandbox root ({root_resolved}): {file_path}")
    return {"resolved": resolved, "relative": relative}


def assert_media_not_data_url(media: str) -> None:
    if DATA_URL_RE.match(media.strip()):
        raise ValueError("data: URLs are not supported for media. Use buffer instead.")


async def resolve_sandboxed_media_source(media: str, sandbox_root: str) -> str:
    raw = media.strip()
    if not raw:
        return raw
    if HTTP_URL_RE.match(raw):
        return raw
    candidate = raw
    if raw.lower().startswith("file://"):
        mapped = _map_container_workspace_file_url(raw, sandbox_root)
        if mapped:
            candidate = mapped
        else:
            parsed = urlparse(raw)
            candidate = unquote(parsed.path)
    container_mapped = _map_container_workspace_path(candidate, sandbox_root)
    if container_mapped:
        candidate = container_mapped
    result = resolve_sandbox_path(candidate, sandbox_root, sandbox_root)
    return result["resolved"]


def _map_container_workspace_file_url(file_url: str, sandbox_root: str) -> str | None:
    parsed = urlparse(file_url)
    if parsed.scheme != "file":
        return None
    normalized = unquote(parsed.path).replace("\\", "/")
    return _map_container_workspace_path(normalized, sandbox_root)


def _map_container_workspace_path(candidate: str, sandbox_root: str) -> str | None:
    normalized = candidate.replace("\\", "/")
    if normalized == SANDBOX_CONTAINER_WORKDIR:
        return os.path.abspath(sandbox_root)
    prefix = f"{SANDBOX_CONTAINER_WORKDIR}/"
    if not normalized.startswith(prefix):
        return None
    rel = normalized[len(prefix):]
    if not rel:
        return os.path.abspath(sandbox_root)
    parts = [p for p in rel.split("/") if p]
    return os.path.abspath(os.path.join(sandbox_root, *parts))

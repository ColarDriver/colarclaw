"""Bootstrap files resolution — ported from bk/src/agents/bootstrap-files.ts.

Loads, filters, and resolves bootstrap context files for agent runs
with support for different context modes (full/lightweight).
"""
from __future__ import annotations

from typing import Any, Literal

from agents.workspace import (
    WorkspaceBootstrapFile,
    filter_bootstrap_files_for_session,
    load_workspace_bootstrap_files,
)

BootstrapContextMode = Literal["full", "lightweight"]
BootstrapContextRunKind = Literal["default", "heartbeat", "cron"]


def make_bootstrap_warn(
    session_label: str,
    warn: Any | None = None,
) -> Any | None:
    """Create a warning function with session context."""
    if warn is None:
        return None
    def _warn(message: str) -> None:
        warn(f"{message} (sessionKey={session_label})")
    return _warn


def _sanitize_bootstrap_files(
    files: list[WorkspaceBootstrapFile],
    warn: Any | None = None,
) -> list[WorkspaceBootstrapFile]:
    sanitized: list[WorkspaceBootstrapFile] = []
    for f in files:
        path_value = f.path.strip() if isinstance(f.path, str) else ""
        if not path_value:
            if warn:
                warn(
                    f'skipping bootstrap file "{f.name}" — missing or invalid '
                    '"path" field (hook may have used "filePath" instead)'
                )
            continue
        sanitized.append(WorkspaceBootstrapFile(
            name=f.name,
            path=path_value,
            content=f.content,
            missing=f.missing,
        ))
    return sanitized


def _apply_context_mode_filter(
    files: list[WorkspaceBootstrapFile],
    context_mode: BootstrapContextMode = "full",
    run_kind: BootstrapContextRunKind = "default",
) -> list[WorkspaceBootstrapFile]:
    if context_mode != "lightweight":
        return files
    if run_kind == "heartbeat":
        return [f for f in files if f.name == "HEARTBEAT.md"]
    return []


async def resolve_bootstrap_files_for_run(
    workspace_dir: str,
    session_key: str | None = None,
    context_mode: BootstrapContextMode = "full",
    run_kind: BootstrapContextRunKind = "default",
    warn: Any | None = None,
    session_label: str | None = None,
) -> list[WorkspaceBootstrapFile]:
    """Resolve bootstrap files for an agent run with filtering and sanitization."""
    raw_files = load_workspace_bootstrap_files(workspace_dir)
    filtered = filter_bootstrap_files_for_session(raw_files, session_key)
    mode_filtered = _apply_context_mode_filter(filtered, context_mode, run_kind)
    label = session_label or session_key or ""
    warn_fn = make_bootstrap_warn(label, warn) if warn else None
    return _sanitize_bootstrap_files(mode_filtered, warn_fn)


def build_bootstrap_context_files(
    bootstrap_files: list[WorkspaceBootstrapFile],
    max_chars: int = 100_000,
    total_max_chars: int = 500_000,
    warn: Any | None = None,
) -> list[dict[str, str]]:
    """Build embedded context files from bootstrap files with truncation.

    Returns:
        List of dicts with 'path' and 'content' keys.
    """
    context_files: list[dict[str, str]] = []
    total_chars = 0

    for f in bootstrap_files:
        if f.missing or not f.content:
            continue

        content = f.content
        if len(content) > max_chars:
            content = content[:max_chars]
            if warn:
                warn(f"Bootstrap file {f.name} truncated to {max_chars} chars")

        if total_chars + len(content) > total_max_chars:
            remaining = total_max_chars - total_chars
            if remaining <= 0:
                break
            content = content[:remaining]
            if warn:
                warn(f"Bootstrap file {f.name} truncated to fit total budget")

        context_files.append({
            "path": f.path or f.name,
            "content": content,
        })
        total_chars += len(content)

    return context_files

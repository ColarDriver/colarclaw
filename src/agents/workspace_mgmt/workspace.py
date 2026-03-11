"""Workspace bootstrap — ported from bk/src/agents/workspace.ts.

Handles workspace directory management, bootstrap file loading
(AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, USER.md, etc.),
frontmatter stripping, and onboarding state tracking.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("openclaw.agents.workspace")

# ── Default filenames ─────────────────────────────────────────────────────
DEFAULT_AGENTS_FILENAME = "AGENTS.md"
DEFAULT_SOUL_FILENAME = "SOUL.md"
DEFAULT_TOOLS_FILENAME = "TOOLS.md"
DEFAULT_IDENTITY_FILENAME = "IDENTITY.md"
DEFAULT_USER_FILENAME = "USER.md"
DEFAULT_HEARTBEAT_FILENAME = "HEARTBEAT.md"
DEFAULT_BOOTSTRAP_FILENAME = "BOOTSTRAP.md"
DEFAULT_MEMORY_FILENAME = "MEMORY.md"
DEFAULT_MEMORY_ALT_FILENAME = "memory.md"

WORKSPACE_STATE_DIRNAME = ".openclaw"
WORKSPACE_STATE_FILENAME = "workspace-state.json"
WORKSPACE_STATE_VERSION = 1
MAX_WORKSPACE_BOOTSTRAP_FILE_BYTES = 2 * 1024 * 1024

VALID_BOOTSTRAP_NAMES: set[str] = {
    DEFAULT_AGENTS_FILENAME,
    DEFAULT_SOUL_FILENAME,
    DEFAULT_TOOLS_FILENAME,
    DEFAULT_IDENTITY_FILENAME,
    DEFAULT_USER_FILENAME,
    DEFAULT_HEARTBEAT_FILENAME,
    DEFAULT_BOOTSTRAP_FILENAME,
    DEFAULT_MEMORY_FILENAME,
    DEFAULT_MEMORY_ALT_FILENAME,
}

MINIMAL_BOOTSTRAP_ALLOWLIST: set[str] = {
    DEFAULT_AGENTS_FILENAME,
    DEFAULT_TOOLS_FILENAME,
    DEFAULT_SOUL_FILENAME,
    DEFAULT_IDENTITY_FILENAME,
    DEFAULT_USER_FILENAME,
}


@dataclass
class WorkspaceBootstrapFile:
    name: str
    path: str
    content: str | None = None
    missing: bool = False


@dataclass
class WorkspaceOnboardingState:
    version: int = WORKSPACE_STATE_VERSION
    bootstrap_seeded_at: str | None = None
    onboarding_completed_at: str | None = None


@dataclass
class ExtraBootstrapLoadDiagnostic:
    path: str
    reason: str  # "invalid-bootstrap-filename" | "missing" | "security" | "io"
    detail: str


# ── Helpers ────────────────────────────────────────────────────────────────

def resolve_default_agent_workspace_dir() -> str:
    """Resolve the default agent workspace directory."""
    home = os.path.expanduser("~")
    profile = os.environ.get("OPENCLAW_PROFILE", "").strip()
    if profile and profile.lower() != "default":
        return os.path.join(home, ".openclaw", f"workspace-{profile}")
    return os.path.join(home, ".openclaw", "workspace")


DEFAULT_AGENT_WORKSPACE_DIR = resolve_default_agent_workspace_dir()


def strip_front_matter(content: str) -> str:
    """Strip YAML front matter from markdown content."""
    if not content.startswith("---"):
        return content
    end_index = content.find("\n---", 3)
    if end_index == -1:
        return content
    start = end_index + len("\n---")
    trimmed = content[start:]
    trimmed = trimmed.lstrip()
    return trimmed


def _resolve_workspace_state_path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, WORKSPACE_STATE_DIRNAME, WORKSPACE_STATE_FILENAME)


def _read_workspace_onboarding_state(state_path: str) -> WorkspaceOnboardingState:
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            raw = f.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return WorkspaceOnboardingState()
        return WorkspaceOnboardingState(
            bootstrap_seeded_at=data.get("bootstrapSeededAt"),
            onboarding_completed_at=data.get("onboardingCompletedAt"),
        )
    except (OSError, json.JSONDecodeError):
        return WorkspaceOnboardingState()


def _write_workspace_onboarding_state(
    state_path: str,
    state: WorkspaceOnboardingState,
) -> None:
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    payload = json.dumps({
        "version": state.version,
        "bootstrapSeededAt": state.bootstrap_seeded_at,
        "onboardingCompletedAt": state.onboarding_completed_at,
    }, indent=2) + "\n"
    tmp_path = f"{state_path}.tmp-{os.getpid()}-{int(datetime.now().timestamp())}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, state_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _read_workspace_file(file_path: str, workspace_dir: str) -> str | None:
    """Read a workspace file with boundary checks."""
    try:
        real_path = os.path.realpath(file_path)
        real_workspace = os.path.realpath(workspace_dir)
        # Boundary check: file must be under workspace
        if not real_path.startswith(real_workspace + os.sep) and real_path != real_workspace:
            log.warning("File %s is outside workspace boundary %s", file_path, workspace_dir)
            return None

        stat = os.stat(real_path)
        if stat.st_size > MAX_WORKSPACE_BOOTSTRAP_FILE_BYTES:
            log.warning("File %s exceeds max size (%d bytes)", file_path, stat.st_size)
            return None

        with open(real_path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, IOError):
        return None


# ── Public API ─────────────────────────────────────────────────────────────

def is_workspace_onboarding_completed(workspace_dir: str) -> bool:
    """Check whether workspace onboarding has been completed."""
    resolved = os.path.expanduser(workspace_dir)
    state_path = _resolve_workspace_state_path(resolved)
    state = _read_workspace_onboarding_state(state_path)
    return bool(state.onboarding_completed_at and state.onboarding_completed_at.strip())


def load_workspace_bootstrap_files(workspace_dir: str) -> list[WorkspaceBootstrapFile]:
    """Load all bootstrap files from a workspace directory."""
    resolved_dir = os.path.expanduser(workspace_dir)

    entries: list[tuple[str, str]] = [
        (DEFAULT_AGENTS_FILENAME, os.path.join(resolved_dir, DEFAULT_AGENTS_FILENAME)),
        (DEFAULT_SOUL_FILENAME, os.path.join(resolved_dir, DEFAULT_SOUL_FILENAME)),
        (DEFAULT_TOOLS_FILENAME, os.path.join(resolved_dir, DEFAULT_TOOLS_FILENAME)),
        (DEFAULT_IDENTITY_FILENAME, os.path.join(resolved_dir, DEFAULT_IDENTITY_FILENAME)),
        (DEFAULT_USER_FILENAME, os.path.join(resolved_dir, DEFAULT_USER_FILENAME)),
        (DEFAULT_HEARTBEAT_FILENAME, os.path.join(resolved_dir, DEFAULT_HEARTBEAT_FILENAME)),
        (DEFAULT_BOOTSTRAP_FILENAME, os.path.join(resolved_dir, DEFAULT_BOOTSTRAP_FILENAME)),
    ]

    # Resolve memory bootstrap entries
    for mem_name in (DEFAULT_MEMORY_FILENAME, DEFAULT_MEMORY_ALT_FILENAME):
        mem_path = os.path.join(resolved_dir, mem_name)
        if os.path.isfile(mem_path):
            entries.append((mem_name, mem_path))

    result: list[WorkspaceBootstrapFile] = []
    for name, file_path in entries:
        content = _read_workspace_file(file_path, resolved_dir)
        if content is not None:
            result.append(WorkspaceBootstrapFile(
                name=name,
                path=file_path,
                content=content,
                missing=False,
            ))
        else:
            result.append(WorkspaceBootstrapFile(
                name=name,
                path=file_path,
                missing=True,
            ))
    return result


def filter_bootstrap_files_for_session(
    files: list[WorkspaceBootstrapFile],
    session_key: str | None = None,
) -> list[WorkspaceBootstrapFile]:
    """Filter bootstrap files for sub-agent/cron sessions (minimal set only)."""
    if not session_key:
        return files
    # Check if session is a subagent or cron session
    is_special = session_key.startswith("subagent:") or session_key.startswith("cron:")
    if not is_special:
        return files
    return [f for f in files if f.name in MINIMAL_BOOTSTRAP_ALLOWLIST]


def ensure_agent_workspace(
    workspace_dir: str | None = None,
    ensure_bootstrap_files: bool = False,
) -> dict[str, str | None]:
    """Ensure a workspace directory exists and optionally seed bootstrap files."""
    raw_dir = (workspace_dir or "").strip() or DEFAULT_AGENT_WORKSPACE_DIR
    resolved_dir = os.path.expanduser(raw_dir)
    os.makedirs(resolved_dir, exist_ok=True)

    result: dict[str, str | None] = {"dir": resolved_dir}
    if not ensure_bootstrap_files:
        return result

    file_names = [
        ("agents_path", DEFAULT_AGENTS_FILENAME),
        ("soul_path", DEFAULT_SOUL_FILENAME),
        ("tools_path", DEFAULT_TOOLS_FILENAME),
        ("identity_path", DEFAULT_IDENTITY_FILENAME),
        ("user_path", DEFAULT_USER_FILENAME),
        ("heartbeat_path", DEFAULT_HEARTBEAT_FILENAME),
        ("bootstrap_path", DEFAULT_BOOTSTRAP_FILENAME),
    ]

    for key, filename in file_names:
        result[key] = os.path.join(resolved_dir, filename)

    return result


def load_extra_bootstrap_files(
    workspace_dir: str,
    extra_patterns: list[str],
) -> list[WorkspaceBootstrapFile]:
    """Load extra bootstrap files from glob patterns."""
    loaded = load_extra_bootstrap_files_with_diagnostics(workspace_dir, extra_patterns)
    return loaded["files"]


def load_extra_bootstrap_files_with_diagnostics(
    workspace_dir: str,
    extra_patterns: list[str],
) -> dict[str, Any]:
    """Load extra bootstrap files with diagnostic information."""
    if not extra_patterns:
        return {"files": [], "diagnostics": []}

    resolved_dir = os.path.expanduser(workspace_dir)
    resolved_paths: set[str] = set()

    for pattern in extra_patterns:
        if any(c in pattern for c in ("*", "?", "{")):
            import glob
            matches = glob.glob(pattern, root_dir=resolved_dir)
            for m in matches:
                resolved_paths.add(m)
        else:
            resolved_paths.add(pattern)

    files: list[WorkspaceBootstrapFile] = []
    diagnostics: list[ExtraBootstrapLoadDiagnostic] = []

    for rel_path in resolved_paths:
        file_path = os.path.join(resolved_dir, rel_path)
        base_name = os.path.basename(rel_path)

        if base_name not in VALID_BOOTSTRAP_NAMES:
            diagnostics.append(ExtraBootstrapLoadDiagnostic(
                path=file_path,
                reason="invalid-bootstrap-filename",
                detail=f"unsupported bootstrap basename: {base_name}",
            ))
            continue

        content = _read_workspace_file(file_path, resolved_dir)
        if content is not None:
            files.append(WorkspaceBootstrapFile(
                name=base_name,
                path=file_path,
                content=content,
                missing=False,
            ))
        else:
            diagnostics.append(ExtraBootstrapLoadDiagnostic(
                path=file_path,
                reason="missing",
                detail="file not found or not readable",
            ))

    return {"files": files, "diagnostics": diagnostics}

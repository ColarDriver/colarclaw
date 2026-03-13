"""Infra platform — ported from bk/src/infra/binaries.ts, brew.ts,
detect-package-manager.ts, git-commit.ts, git-root.ts, gemini-auth.ts,
minimax-portal-auth.ts, google-gemini-cli-auth.ts, canvas-host-url.ts,
control-ui-assets.ts, cli-root-options.ts, windows-*.ts, etc.

Platform helpers: binary resolution, package managers, Git ops, auth,
UI assets, CLI options, channel activity/summary/status.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─── binaries.ts ───

def resolve_binary_path(name: str, search_in: list[str] | None = None) -> str | None:
    if search_in:
        for directory in search_in:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return shutil.which(name)


def is_binary_available(name: str) -> bool:
    return resolve_binary_path(name) is not None


def get_node_binary() -> str | None:
    return resolve_binary_path("node")


def get_npm_binary() -> str | None:
    return resolve_binary_path("npm")


def get_python_binary() -> str | None:
    return resolve_binary_path("python3") or resolve_binary_path("python")


# ─── detect-package-manager.ts ───

def detect_package_manager(dir: str = ".") -> str:
    if os.path.isfile(os.path.join(dir, "bun.lockb")):
        return "bun"
    if os.path.isfile(os.path.join(dir, "yarn.lock")):
        return "yarn"
    if os.path.isfile(os.path.join(dir, "pnpm-lock.yaml")):
        return "pnpm"
    if os.path.isfile(os.path.join(dir, "package-lock.json")):
        return "npm"
    return "npm"


# ─── brew.ts ───

def is_homebrew_installed() -> bool:
    return shutil.which("brew") is not None


def brew_install(package: str, cask: bool = False) -> bool:
    cmd = ["brew", "install"]
    if cask:
        cmd.append("--cask")
    cmd.append(package)
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ─── git-commit.ts / git-root.ts ───

def get_git_root(cwd: str | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_git_commit_hash(cwd: str | None = None, short: bool = False) -> str | None:
    try:
        args = ["git", "rev-parse"]
        if short:
            args.append("--short")
        args.append("HEAD")
        result = subprocess.run(args, capture_output=True, text=True, cwd=cwd, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_git_branch(cwd: str | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def is_git_dirty(cwd: str | None = None) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=cwd, check=True,
        )
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ─── canvas-host-url.ts ───

def resolve_canvas_host_url(config: Any = None, default: str = "http://localhost:3000") -> str:
    if isinstance(config, dict):
        return config.get("canvas_host_url") or config.get("canvasHostUrl") or default
    return os.environ.get("OPENCLAW_CANVAS_HOST_URL", default)


# ─── control-ui-assets.ts ───

def resolve_control_ui_assets_path(workspace_dir: str | None = None) -> str | None:
    candidates = []
    if workspace_dir:
        candidates.append(os.path.join(workspace_dir, "ui", "dist"))
        candidates.append(os.path.join(workspace_dir, "control-ui", "dist"))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


# ─── cli-root-options.ts ───

@dataclass
class CliRootOptions:
    workspace_dir: str | None = None
    config_path: str | None = None
    agent_id: str | None = None
    verbose: bool = False
    debug: bool = False
    quiet: bool = False
    log_level: str = "info"
    port: int | None = None
    host: str | None = None


# ─── channel-activity.ts / channel-summary.ts / channels-status-issues.ts ───

@dataclass
class ChannelActivity:
    channel: str = ""
    account_id: str = ""
    last_inbound_at: float | None = None
    last_outbound_at: float | None = None
    inbound_count: int = 0
    outbound_count: int = 0


@dataclass
class ChannelSummary:
    channel: str = ""
    configured: bool = False
    enabled: bool = False
    running: bool = False
    accounts: int = 0
    issues: list[str] = field(default_factory=list)


@dataclass
class ChannelStatusIssue:
    channel: str = ""
    account_id: str = ""
    kind: str = "error"
    message: str = ""
    severity: str = "warn"


def collect_all_channel_status_issues(channels: list[ChannelSummary]) -> list[ChannelStatusIssue]:
    issues: list[ChannelStatusIssue] = []
    for ch in channels:
        for msg in ch.issues:
            issues.append(ChannelStatusIssue(channel=ch.channel, message=msg))
    return issues


# ─── gemini-auth.ts / google-gemini-cli-auth.ts ───

def resolve_gemini_api_key(config: Any = None) -> str | None:
    if isinstance(config, dict):
        key = config.get("gemini_api_key") or config.get("GEMINI_API_KEY")
        if key:
            return str(key).strip()
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def resolve_google_gemini_cli_auth() -> dict[str, Any]:
    """Resolve auth for Google Gemini CLI (placeholder)."""
    api_key = resolve_gemini_api_key()
    return {"authenticated": bool(api_key), "api_key": api_key}


# ─── minimax-portal-auth.ts ───

def resolve_minimax_api_key(config: Any = None) -> str | None:
    if isinstance(config, dict):
        return config.get("minimax_api_key") or config.get("MINIMAX_API_KEY")
    return os.environ.get("MINIMAX_API_KEY") or os.environ.get("MINIMAX_GROUP_ID")

"""System prompt params — ported from bk/src/agents/system-prompt-params.ts.

Building runtime parameters for system prompt generation.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeInfoInput:
    agent_id: str | None = None
    host: str = ""
    os: str = ""
    arch: str = ""
    node: str = ""
    model: str = ""
    default_model: str | None = None
    shell: str | None = None
    channel: str | None = None
    capabilities: list[str] | None = None
    channel_actions: list[str] | None = None
    repo_root: str | None = None


@dataclass
class SystemPromptRuntimeParams:
    runtime_info: RuntimeInfoInput
    user_timezone: str = "UTC"
    user_time: str | None = None
    user_time_format: str | None = None


def _find_git_root(start_dir: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start_dir, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _resolve_repo_root(
    config: Any | None = None,
    workspace_dir: str | None = None,
    cwd: str | None = None,
) -> str | None:
    # Check config
    if config:
        configured = getattr(getattr(getattr(config, "agents", None), "defaults", None), "repo_root", None)
        if configured and isinstance(configured, str) and configured.strip():
            resolved = os.path.abspath(configured.strip())
            if os.path.isdir(resolved):
                return resolved

    # Try candidates
    seen: set[str] = set()
    for candidate in [workspace_dir, cwd]:
        if not candidate or not candidate.strip():
            continue
        resolved = os.path.abspath(candidate.strip())
        if resolved in seen:
            continue
        seen.add(resolved)
        root = _find_git_root(resolved)
        if root:
            return root
    return None


def build_system_prompt_params(
    runtime: RuntimeInfoInput,
    config: Any | None = None,
    agent_id: str | None = None,
    workspace_dir: str | None = None,
    cwd: str | None = None,
) -> SystemPromptRuntimeParams:
    """Build runtime parameters for system prompt generation."""
    from .date_time import format_user_time, resolve_user_timezone

    repo_root = _resolve_repo_root(config=config, workspace_dir=workspace_dir, cwd=cwd)
    user_timezone = resolve_user_timezone()

    import datetime
    user_time = format_user_time(datetime.datetime.now(datetime.timezone.utc), user_timezone)

    runtime_info = RuntimeInfoInput(
        agent_id=agent_id or runtime.agent_id,
        host=runtime.host, os=runtime.os, arch=runtime.arch,
        node=runtime.node, model=runtime.model,
        default_model=runtime.default_model,
        shell=runtime.shell, channel=runtime.channel,
        capabilities=runtime.capabilities,
        channel_actions=runtime.channel_actions,
        repo_root=repo_root,
    )

    return SystemPromptRuntimeParams(
        runtime_info=runtime_info,
        user_timezone=user_timezone,
        user_time=user_time,
    )

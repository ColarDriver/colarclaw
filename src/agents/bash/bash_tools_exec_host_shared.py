"""Bash tools exec host shared — ported from bk/src/agents/bash-tools.exec-host-shared.ts."""
from __future__ import annotations

import os
from typing import Any


def resolve_exec_shell() -> str:
    """Resolve the shell to use for execution."""
    shell = os.environ.get("SHELL", "").strip()
    if shell:
        return shell
    if os.name == "nt":
        return os.environ.get("COMSPEC", "cmd.exe")
    return "/bin/bash"


def resolve_exec_cwd(cwd: str | None = None, workspace_dir: str | None = None) -> str:
    """Resolve the current working directory for execution."""
    if cwd and os.path.isdir(cwd):
        return cwd
    if workspace_dir and os.path.isdir(workspace_dir):
        return workspace_dir
    return os.getcwd()


def build_exec_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build the environment for execution."""
    env = dict(os.environ)
    env["PAGER"] = "cat"
    env["GIT_PAGER"] = "cat"
    if extra_env:
        env.update(extra_env)
    return env

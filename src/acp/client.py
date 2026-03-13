"""ACP client — ported from bk/src/acp/client.ts.

ACP client: tool permission resolution, subprocess spawning,
interactive prompt session.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable

SAFE_AUTO_APPROVE_TOOL_IDS = frozenset(["read", "search", "web_search", "memory_search"])
TRUSTED_SAFE_TOOL_ALIASES = frozenset(["search"])
READ_TOOL_PATH_KEYS = ["path", "file_path", "filePath"]
TOOL_NAME_MAX_LENGTH = 128
TOOL_NAME_PATTERN = re.compile(r"^[a-z0-9._-]+$")
TOOL_KIND_BY_ID = {"read": "read", "search": "search", "web_search": "search", "memory_search": "search"}
DANGEROUS_ACP_TOOLS: frozenset[str] = frozenset()


def _as_record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _read_first_string(source: dict[str, Any] | None, keys: list[str]) -> str | None:
    if not source:
        return None
    for key in keys:
        v = source.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def normalize_tool_name(value: str) -> str | None:
    n = value.strip().lower()
    if not n or len(n) > TOOL_NAME_MAX_LENGTH or not TOOL_NAME_PATTERN.match(n):
        return None
    return n


def resolve_tool_name_for_permission(params: dict[str, Any]) -> str | None:
    tool_call = params.get("toolCall")
    meta = _as_record(tool_call.get("_meta")) if isinstance(tool_call, dict) else None
    raw_input = _as_record(tool_call.get("rawInput")) if isinstance(tool_call, dict) else None
    from_meta = _read_first_string(meta, ["toolName", "tool_name", "name"])
    from_raw = _read_first_string(raw_input, ["tool", "toolName", "tool_name", "name"])
    title = tool_call.get("title") if isinstance(tool_call, dict) else None
    from_title = _parse_tool_name_from_title(title)
    return normalize_tool_name(from_meta or from_raw or from_title or "")


def _parse_tool_name_from_title(title: str | None) -> str | None:
    if not title:
        return None
    head = title.split(":", 1)[0].strip()
    return normalize_tool_name(head) if head else None


def should_auto_approve_tool_call(
    params: dict[str, Any],
    tool_name: str | None,
    tool_title: str | None,
    cwd: str,
) -> bool:
    if not tool_name or tool_name not in SAFE_AUTO_APPROVE_TOOL_IDS:
        return False
    if tool_name == "read":
        return _is_read_scoped_to_cwd(params, tool_name, tool_title, cwd)
    return True


def _is_read_scoped_to_cwd(
    params: dict[str, Any],
    tool_name: str | None,
    tool_title: str | None,
    cwd: str,
) -> bool:
    if tool_name != "read":
        return False
    raw_input = _as_record((params.get("toolCall") or {}).get("rawInput"))
    raw_path = _read_first_string(raw_input, READ_TOOL_PATH_KEYS)
    if not raw_path:
        return False
    candidate = raw_path.strip()
    if candidate.startswith("~"):
        candidate = os.path.expanduser(candidate)
    absolute = os.path.abspath(os.path.join(cwd, candidate) if not os.path.isabs(candidate) else candidate)
    resolved_cwd = os.path.abspath(cwd)
    return absolute.startswith(resolved_cwd)


@dataclass
class AcpClientOptions:
    cwd: str | None = None
    server_command: str | None = None
    server_args: list[str] | None = None
    server_verbose: bool = False
    verbose: bool = False


@dataclass
class AcpClientHandle:
    client: Any = None
    agent: Any = None
    session_id: str = ""


def resolve_acp_client_spawn_env(
    base_env: dict[str, str] | None = None,
    strip_keys: set[str] | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    if strip_keys:
        for key in strip_keys:
            env.pop(key, None)
    env["OPENCLAW_SHELL"] = "acp-client"
    return env


async def create_acp_client(opts: AcpClientOptions | None = None) -> AcpClientHandle:
    """Create an ACP client handle (placeholder — real impl spawns subprocess)."""
    return AcpClientHandle(session_id="")


async def run_acp_client_interactive(opts: AcpClientOptions | None = None) -> None:
    """Run interactive ACP client session (placeholder)."""
    pass

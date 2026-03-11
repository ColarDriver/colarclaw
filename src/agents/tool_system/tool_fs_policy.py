"""Tool filesystem policy — ported from bk/src/agents/tool-fs-policy.ts."""
from __future__ import annotations
import os
from typing import Any

ALWAYS_DENY_PATHS = frozenset({
    "/etc/shadow", "/etc/passwd",
    "/proc", "/sys",
    "/dev",
})

ALWAYS_DENY_PATTERNS = [
    ".ssh/id_", ".ssh/authorized_keys",
    ".gnupg/", ".pgp/",
    "node_modules/.cache",
]

def is_path_denied(path: str) -> bool:
    normalized = os.path.normpath(path)
    if normalized in ALWAYS_DENY_PATHS:
        return True
    return any(pattern in normalized for pattern in ALWAYS_DENY_PATTERNS)

def resolve_fs_policy_for_tool(
    tool_name: str,
    sandbox_root: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool": tool_name,
        "sandboxRoot": sandbox_root,
        "readOnly": tool_name in ("read", "cat", "ls", "find", "grep"),
        "pathDenyList": list(ALWAYS_DENY_PATHS),
    }

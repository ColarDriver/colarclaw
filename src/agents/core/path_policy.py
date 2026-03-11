"""Path policy — ported from bk/src/agents/path-policy.ts.

Filesystem path access policy for sandboxed tool execution.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

PathAccess = Literal["allow", "deny", "readonly"]

@dataclass
class PathPolicyRule:
    pattern: str
    access: PathAccess
    compiled: re.Pattern[str] | None = None

@dataclass
class PathPolicy:
    rules: list[PathPolicyRule] = field(default_factory=list)
    default_access: PathAccess = "allow"

def compile_path_rule(pattern: str, access: PathAccess) -> PathPolicyRule:
    escaped = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return PathPolicyRule(pattern=pattern, access=access, compiled=re.compile(f"^{escaped}$"))

def build_path_policy(rules: list[dict[str, str]] | None = None, default_access: PathAccess = "allow") -> PathPolicy:
    if not rules:
        return PathPolicy(default_access=default_access)
    compiled = [compile_path_rule(r.get("pattern", ""), r.get("access", "allow")) for r in rules]  # type: ignore
    return PathPolicy(rules=compiled, default_access=default_access)

def check_path_access(policy: PathPolicy, path: str) -> PathAccess:
    normalized = os.path.normpath(path)
    for rule in reversed(policy.rules):
        if rule.compiled and rule.compiled.match(normalized):
            return rule.access
    return policy.default_access

def is_path_writable(policy: PathPolicy, path: str) -> bool:
    return check_path_access(policy, path) == "allow"

def is_path_readable(policy: PathPolicy, path: str) -> bool:
    access = check_path_access(policy, path)
    return access in ("allow", "readonly")

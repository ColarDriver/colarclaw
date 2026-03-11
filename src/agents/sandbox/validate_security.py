"""Sandbox validate security — ported from bk/src/agents/sandbox/validate-sandbox-security.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SecurityValidationResult:
    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_sandbox_security(
    config: Any = None,
) -> SecurityValidationResult:
    """Validate sandbox security configuration."""
    result = SecurityValidationResult()
    if not config:
        return result

    sandbox = getattr(config, "sandbox", None)
    if not sandbox or not getattr(sandbox, "enabled", False):
        return result

    # Check network access
    if getattr(sandbox, "network", True):
        result.warnings.append("Sandbox has network access enabled")

    # Check workspace access
    access = getattr(sandbox, "workspace_access", "read-write")
    if access == "read-write":
        result.warnings.append("Sandbox has read-write workspace access")

    return result

"""ACP control plane runtime options — ported from bk/src/acp/control-plane/runtime-options.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AcpRuntimeOptions:
    cwd: str | None = None
    tool_use: bool = True
    thinking: str | None = None
    verbose: bool = False
    system_prompt: str | None = None


def resolve_runtime_options(cfg: Any = None, patch: dict[str, Any] | None = None) -> AcpRuntimeOptions:
    opts = AcpRuntimeOptions()
    if patch:
        for key, value in patch.items():
            if hasattr(opts, key):
                setattr(opts, key, value)
    return opts

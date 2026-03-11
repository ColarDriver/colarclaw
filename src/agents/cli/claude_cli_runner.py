"""Claude CLI runner — ported from bk/src/agents/claude-cli-runner.ts.

Backwards-compatible entry point. Implementation should live in cli_runner.
"""
from __future__ import annotations

# Re-export from the CLI runner module for backwards compatibility.
# Actual implementation lives in cli_runner if present.
try:
    from .cli_runner import run_claude_cli_agent, run_cli_agent
except ImportError:
    async def run_cli_agent(*args, **kwargs):
        raise NotImplementedError("cli_runner module not yet available")

    async def run_claude_cli_agent(*args, **kwargs):
        return await run_cli_agent(*args, **kwargs)

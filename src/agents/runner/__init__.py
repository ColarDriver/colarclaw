"""Agent runner — embedded agent execution engine.

Ported from openclaw/src/agents/pi-embedded-runner/

This package provides the core agent run loop:
- AgentRunner: orchestrates memory → tools → prompt → LLM → store
- AgentRunState: mutable state for a single run
- ToolEvent: tool call event record
- build_embedded_system_prompt: system prompt builder
"""
from .run import AgentRunner
from .types import AgentRunMeta, AgentRunResult, AgentRunState, ToolEvent
from .system_prompt import build_embedded_system_prompt

__all__ = [
    "AgentRunner",
    "AgentRunMeta",
    "AgentRunResult",
    "AgentRunState",
    "ToolEvent",
    "build_embedded_system_prompt",
]

"""Reply agent runner — ported from bk/src/auto-reply/reply/agent-runner.ts + helpers + utils + payloads + execution + memory."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentRunnerConfig:
    model: str = ""
    provider: str = ""
    system_prompt: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    sandbox_enabled: bool = False


@dataclass
class RuntimeFallbackAttempt:
    provider: str = ""
    model: str = ""
    error: str = ""
    reason: str | None = None
    code: str | None = None
    status: int | None = None


async def run_reply_agent(
    ctx: Any,
    cfg: Any,
    runner_config: AgentRunnerConfig | None = None,
) -> dict[str, Any]:
    """Main entry point for running the reply agent."""
    return {"status": "completed", "text": ""}


def build_agent_runner_payloads(
    system_prompt: str,
    user_message: str,
    history: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


def resolve_agent_memory_context(
    session_id: str | None = None,
    max_entries: int = 50,
) -> list[dict[str, Any]]:
    return []


def format_tool_result_for_display(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        import json
        return json.dumps(result, indent=2, ensure_ascii=False)
    return str(result)


def resolve_reminder_guard(
    message: str, config: Any = None,
) -> str:
    return message

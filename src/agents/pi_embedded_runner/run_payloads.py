"""Pi embedded runner run payloads — ported from bk/src/agents/pi-embedded-runner/run/payloads.ts."""
from __future__ import annotations

import json
from typing import Any


def build_chat_payload(
    messages: list[dict[str, Any]],
    model: str,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    **extra: Any,
) -> dict[str, Any]:
    """Build the chat completion API payload."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
    payload.update(extra)
    return payload


def build_user_message(content: str) -> dict[str, Any]:
    return {"role": "user", "content": content}


def build_assistant_message(content: str, tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def build_tool_result_message(tool_call_id: str, content: str) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def build_system_message(content: str) -> dict[str, Any]:
    return {"role": "system", "content": content}

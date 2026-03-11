"""Session tool result guard.

Ported and extended from ``bk/src/agents/session-tool-result-guard*.ts``.
Provides basic tool-result size guarding and an installable session-manager
wrapper that enforces pairing/sanitization for appended transcript messages.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agents.session_tool_result_state import (
    PendingToolCall,
    create_pending_tool_call_state,
)
from agents.tool_call_id import extract_tool_calls_from_assistant, extract_tool_result_id
from session.transcript_repair import make_missing_tool_result, sanitize_tool_call_inputs

log = logging.getLogger("openclaw.agents.session_tool_result_guard")

MAX_TOOL_RESULT_SIZE = 100_000  # chars
HARD_MAX_TOOL_RESULT_CHARS = MAX_TOOL_RESULT_SIZE
GUARD_TRUNCATION_SUFFIX = (
    "\n\n⚠️ [Content truncated during persistence — original exceeded size limit. "
    "Use offset/limit parameters or request specific sections for large content.]"
)


@dataclass
class ToolResultGuardState:
    """Aggregate counters for guarded tool results."""

    total_chars: int = 0
    total_results: int = 0
    truncated_count: int = 0


@dataclass
class GuardedToolResult:
    """Result payload returned from `guard_tool_result`."""

    tool_call_id: str
    content: Any
    is_error: bool = False
    truncated: bool = False
    original_size: int = 0


@dataclass
class SessionToolResultGuardHandle:
    """Handle returned by `install_session_tool_result_guard`."""

    flush_pending_tool_results: Any
    clear_pending_tool_results: Any
    get_pending_ids: Any


def _cap_tool_result_size_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Cap tool result text content size in a transcript message."""
    if msg.get("role") != "toolResult":
        return msg

    content = msg.get("content")
    if isinstance(content, str):
        if len(content) <= HARD_MAX_TOOL_RESULT_CHARS:
            return msg
        return {
            **msg,
            "content": content[:HARD_MAX_TOOL_RESULT_CHARS] + GUARD_TRUNCATION_SUFFIX,
        }

    if not isinstance(content, list):
        return msg

    total = 0
    changed = False
    next_content: list[Any] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            next_content.append(block)
            continue
        text = block.get("text")
        if not isinstance(text, str):
            next_content.append(block)
            continue

        if total >= HARD_MAX_TOOL_RESULT_CHARS:
            changed = True
            continue

        remaining = HARD_MAX_TOOL_RESULT_CHARS - total
        if len(text) <= remaining:
            total += len(text)
            next_content.append(block)
            continue

        changed = True
        clipped = text[:remaining] + GUARD_TRUNCATION_SUFFIX
        total += len(text[:remaining])
        next_content.append({**block, "text": clipped})

    return {**msg, "content": next_content} if changed else msg


def _trim_non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalize_persisted_tool_result_name(
    message: dict[str, Any],
    fallback_name: str | None = None,
) -> dict[str, Any]:
    """Normalize toolResult.toolName similar to TS guard behavior."""
    if message.get("role") != "toolResult":
        return message

    raw_tool_name = message.get("toolName")
    normalized_tool_name = _trim_non_empty_string(raw_tool_name)
    if normalized_tool_name:
        if raw_tool_name == normalized_tool_name:
            return message
        return {**message, "toolName": normalized_tool_name}

    normalized_fallback = _trim_non_empty_string(fallback_name)
    if normalized_fallback:
        return {**message, "toolName": normalized_fallback}

    if isinstance(raw_tool_name, str):
        return {**message, "toolName": "unknown"}
    return message


def guard_tool_result(
    tool_call_id: str,
    content: Any,
    is_error: bool = False,
    max_size: int = MAX_TOOL_RESULT_SIZE,
    state: ToolResultGuardState | None = None,
) -> GuardedToolResult:
    """Guard one tool result payload by truncating oversized text content."""
    if isinstance(content, str):
        original_size = len(content)
        truncated = original_size > max_size
        if truncated:
            content = content[:max_size] + f"\n\n[truncated: {original_size - max_size} chars omitted]"
        if state:
            state.total_chars += len(content)
            state.total_results += 1
            if truncated:
                state.truncated_count += 1
        return GuardedToolResult(
            tool_call_id=tool_call_id,
            content=content,
            is_error=is_error,
            truncated=truncated,
            original_size=original_size,
        )

    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
        total_text = "\n".join(text_parts)
        original_size = len(total_text)
        if original_size > max_size:
            return guard_tool_result(tool_call_id, total_text, is_error, max_size, state)

    return GuardedToolResult(tool_call_id=tool_call_id, content=content, is_error=is_error)


def create_guard_state() -> ToolResultGuardState:
    """Create an empty guard state accumulator."""
    return ToolResultGuardState()


def install_session_tool_result_guard(
    session_manager: Any,
    opts: dict[str, Any] | None = None,
) -> SessionToolResultGuardHandle:
    """Install guard behavior around `session_manager.append_message` exactly once."""
    existing_flush = getattr(session_manager, "flush_pending_tool_results", None)
    if callable(existing_flush):
        return SessionToolResultGuardHandle(
            flush_pending_tool_results=existing_flush,
            clear_pending_tool_results=getattr(session_manager, "clear_pending_tool_results", lambda: None),
            get_pending_ids=getattr(session_manager, "get_pending_tool_result_ids", lambda: []),
        )

    if not hasattr(session_manager, "append_message"):
        raise AttributeError("session_manager must expose append_message(message)")

    options = opts or {}
    transform_message = options.get("transform_message_for_persistence")
    transform_tool_result = options.get("transform_tool_result_for_persistence")
    before_write_hook = options.get("before_message_write_hook")
    allowed_tool_names = options.get("allowed_tool_names")
    allow_synthetic_tool_results = options.get("allow_synthetic_tool_results", True)

    pending_state = create_pending_tool_call_state()
    original_append = session_manager.append_message

    def _persist_message(message: dict[str, Any]) -> dict[str, Any]:
        if callable(transform_message):
            return transform_message(message)
        return message

    def _persist_tool_result(
        message: dict[str, Any],
        meta: dict[str, Any],
    ) -> dict[str, Any]:
        if callable(transform_tool_result):
            return transform_tool_result(message, meta)
        return message

    def _apply_before_write_hook(message: dict[str, Any]) -> dict[str, Any] | None:
        if not callable(before_write_hook):
            return message
        result = before_write_hook({"message": message})
        if isinstance(result, dict):
            if result.get("block"):
                return None
            candidate = result.get("message")
            if isinstance(candidate, dict):
                return candidate
        return message

    def flush_pending_tool_results() -> None:
        if pending_state.size() == 0:
            return
        if allow_synthetic_tool_results:
            for tool_call_id, tool_name in pending_state.entries():
                synthetic = make_missing_tool_result(tool_call_id, tool_name)
                synthetic_msg = _persist_message(synthetic)
                synthetic_msg = _persist_tool_result(
                    synthetic_msg,
                    {
                        "toolCallId": tool_call_id,
                        "toolName": tool_name,
                        "isSynthetic": True,
                    },
                )
                final_msg = _apply_before_write_hook(synthetic_msg)
                if isinstance(final_msg, dict):
                    original_append(final_msg)
        pending_state.clear()

    def clear_pending_tool_results() -> None:
        pending_state.clear()

    def get_pending_ids() -> list[str]:
        return pending_state.get_pending_ids()

    def guarded_append(message: dict[str, Any]) -> Any:
        next_message: dict[str, Any] = message
        role = message.get("role")

        if role == "assistant":
            allowed_names_list = list(allowed_tool_names) if allowed_tool_names is not None else None
            sanitized = sanitize_tool_call_inputs([message], allowed_names_list)
            if not sanitized:
                if pending_state.should_flush_for_sanitized_drop():
                    flush_pending_tool_results()
                return None
            next_message = sanitized[0]

        next_role = next_message.get("role")

        if next_role == "toolResult":
            result_id = extract_tool_result_id(next_message)
            tool_name = pending_state.get_tool_name(result_id) if isinstance(result_id, str) else None
            if isinstance(result_id, str):
                pending_state.delete(result_id)

            normalized = _normalize_persisted_tool_result_name(next_message, tool_name)
            capped = _cap_tool_result_size_message(_persist_message(normalized))
            persisted = _persist_tool_result(
                capped,
                {
                    "toolCallId": result_id,
                    "toolName": tool_name,
                    "isSynthetic": False,
                },
            )
            final_msg = _apply_before_write_hook(persisted)
            if not isinstance(final_msg, dict):
                return None
            return original_append(final_msg)

        stop_reason = next_message.get("stopReason")
        tool_calls_raw = (
            extract_tool_calls_from_assistant(next_message)
            if next_role == "assistant" and stop_reason not in {"aborted", "error"}
            else []
        )
        tool_calls = [
            PendingToolCall(id=call["id"], name=(call.get("name") or None))
            for call in tool_calls_raw
            if isinstance(call, dict) and isinstance(call.get("id"), str)
        ]

        if pending_state.should_flush_before_non_tool_result(next_role, len(tool_calls)):
            flush_pending_tool_results()
        if pending_state.should_flush_before_new_tool_calls(len(tool_calls)):
            flush_pending_tool_results()

        persisted_message = _persist_message(next_message)
        final_msg = _apply_before_write_hook(persisted_message)
        if not isinstance(final_msg, dict):
            return None

        result = original_append(final_msg)

        if tool_calls:
            pending_state.track_tool_calls(tool_calls)

        return result

    session_manager.append_message = guarded_append
    session_manager.flush_pending_tool_results = flush_pending_tool_results
    session_manager.clear_pending_tool_results = clear_pending_tool_results
    session_manager.get_pending_tool_result_ids = get_pending_ids

    return SessionToolResultGuardHandle(
        flush_pending_tool_results=flush_pending_tool_results,
        clear_pending_tool_results=clear_pending_tool_results,
        get_pending_ids=get_pending_ids,
    )


__all__ = [
    "MAX_TOOL_RESULT_SIZE",
    "ToolResultGuardState",
    "GuardedToolResult",
    "SessionToolResultGuardHandle",
    "guard_tool_result",
    "create_guard_state",
    "install_session_tool_result_guard",
]

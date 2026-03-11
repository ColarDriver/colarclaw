"""Session transcript repair — ported from bk/src/agents/session-transcript-repair.ts.

Repairs session transcripts to satisfy provider requirements:
- Removes tool calls without valid input, ID, or name
- Ensures tool call / tool result pairing (Anthropic requirement)
- Inserts synthetic error results for missing tool results
- Drops duplicate/orphan tool results
- Redacts sessions_spawn attachment content
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

TOOL_CALL_NAME_MAX_CHARS = 64
TOOL_CALL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _is_raw_tool_call_block(block: Any) -> bool:
    """Check if a content block is a tool call."""
    if not isinstance(block, dict):
        return False
    block_type = block.get("type")
    return block_type in ("toolCall", "toolUse", "functionCall")


def _has_tool_call_input(block: dict) -> bool:
    has_input = block.get("input") is not None
    has_arguments = block.get("arguments") is not None
    return has_input or has_arguments


def _has_tool_call_id(block: dict) -> bool:
    block_id = block.get("id")
    return isinstance(block_id, str) and block_id.strip() != ""


def _has_tool_call_name(block: dict, allowed_names: set[str] | None) -> bool:
    name = block.get("name")
    if not isinstance(name, str):
        return False
    trimmed = name.strip()
    if not trimmed:
        return False
    if len(trimmed) > TOOL_CALL_NAME_MAX_CHARS or not TOOL_CALL_NAME_RE.match(trimmed):
        return False
    if allowed_names is None:
        return True
    return trimmed.lower() in allowed_names


def _normalize_allowed_tool_names(names: list[str] | None) -> set[str] | None:
    if not names:
        return None
    normalized = set()
    for name in names:
        if isinstance(name, str):
            trimmed = name.strip()
            if trimmed:
                normalized.add(trimmed.lower())
    return normalized if normalized else None


def _redact_sessions_spawn_attachments(value: Any) -> Any:
    """Redact large inline attachment content from sessions_spawn args."""
    if not isinstance(value, dict):
        return value
    attachments = value.get("attachments")
    if not isinstance(attachments, list):
        return value
    redacted = []
    for item in attachments:
        if not isinstance(item, dict) or "content" not in item:
            redacted.append(item)
            continue
        next_item = {k: v for k, v in item.items() if k != "content"}
        next_item["content"] = "__OPENCLAW_REDACTED__"
        redacted.append(next_item)
    return {**value, "attachments": redacted}


def _sanitize_tool_call_block(block: dict) -> dict:
    """Sanitize a tool call block (trim name, redact sessions_spawn attachments)."""
    raw_name = block.get("name")
    trimmed_name = raw_name.strip() if isinstance(raw_name, str) else None
    has_trimmed = bool(trimmed_name)
    name_changed = has_trimmed and raw_name != trimmed_name

    is_sessions_spawn = trimmed_name and trimmed_name.lower() == "sessions_spawn"

    if not is_sessions_spawn:
        if not name_changed:
            return block
        return {**block, "name": trimmed_name}

    next_args = _redact_sessions_spawn_attachments(block.get("arguments"))
    next_input = _redact_sessions_spawn_attachments(block.get("input"))

    if next_args is block.get("arguments") and next_input is block.get("input") and not name_changed:
        return block

    result = dict(block)
    if name_changed and trimmed_name:
        result["name"] = trimmed_name
    if "arguments" in block:
        result["arguments"] = next_args
    if "input" in block:
        result["input"] = next_input
    return result


def make_missing_tool_result(tool_call_id: str, tool_name: str | None = None) -> dict:
    """Create a synthetic error tool result for a missing result."""
    return {
        "role": "toolResult",
        "toolCallId": tool_call_id,
        "toolName": tool_name or "unknown",
        "content": [{
            "type": "text",
            "text": "[openclaw] missing tool result in session history; "
                    "inserted synthetic error result for transcript repair.",
        }],
        "isError": True,
        "timestamp": int(time.time() * 1000),
    }


def _extract_tool_calls_from_assistant(msg: dict) -> list[dict[str, str]]:
    """Extract tool call IDs and names from an assistant message."""
    content = msg.get("content")
    if not isinstance(content, list):
        return []
    calls = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type not in ("toolCall", "toolUse", "functionCall"):
            continue
        call_id = block.get("id", "")
        call_name = block.get("name", "")
        if isinstance(call_id, str) and call_id.strip():
            calls.append({"id": call_id.strip(), "name": call_name if isinstance(call_name, str) else ""})
    return calls


def _extract_tool_result_id(msg: dict) -> str | None:
    """Extract the tool call ID from a tool result message."""
    tool_call_id = msg.get("toolCallId")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        return tool_call_id.strip()
    return None


# ── Public API ─────────────────────────────────────────────────────────────

@dataclass
class ToolCallInputRepairReport:
    messages: list[dict]
    dropped_tool_calls: int = 0
    dropped_assistant_messages: int = 0


@dataclass
class ToolUseRepairReport:
    messages: list[dict]
    added: list[dict] = field(default_factory=list)
    dropped_duplicate_count: int = 0
    dropped_orphan_count: int = 0
    moved: bool = False


def strip_tool_result_details(messages: list[dict]) -> list[dict]:
    """Remove the 'details' field from toolResult messages."""
    touched = False
    out: list[dict] = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "toolResult":
            out.append(msg)
            continue
        if "details" not in msg:
            out.append(msg)
            continue
        sanitized = {k: v for k, v in msg.items() if k != "details"}
        touched = True
        out.append(sanitized)
    return out if touched else messages


def repair_tool_call_inputs(
    messages: list[dict],
    allowed_tool_names: list[str] | None = None,
) -> ToolCallInputRepairReport:
    """Repair tool call inputs by removing invalid tool calls."""
    dropped_tool_calls = 0
    dropped_assistant_messages = 0
    changed = False
    out: list[dict] = []
    allowed = _normalize_allowed_tool_names(allowed_tool_names)

    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        if msg.get("role") != "assistant" or not isinstance(msg.get("content"), list):
            out.append(msg)
            continue

        next_content: list[Any] = []
        dropped_in_msg = 0
        msg_changed = False

        for block in msg["content"]:
            if (
                _is_raw_tool_call_block(block)
                and (
                    not _has_tool_call_input(block)
                    or not _has_tool_call_id(block)
                    or not _has_tool_call_name(block, allowed)
                )
            ):
                dropped_tool_calls += 1
                dropped_in_msg += 1
                changed = True
                msg_changed = True
                continue

            if _is_raw_tool_call_block(block):
                sanitized = _sanitize_tool_call_block(block)
                if sanitized is not block:
                    changed = True
                    msg_changed = True
                next_content.append(sanitized)
            else:
                next_content.append(block)

        if dropped_in_msg > 0 and not next_content:
            dropped_assistant_messages += 1
            changed = True
            continue
        if dropped_in_msg > 0 or msg_changed:
            out.append({**msg, "content": next_content})
            continue
        out.append(msg)

    return ToolCallInputRepairReport(
        messages=out if changed else messages,
        dropped_tool_calls=dropped_tool_calls,
        dropped_assistant_messages=dropped_assistant_messages,
    )


def sanitize_tool_call_inputs(
    messages: list[dict],
    allowed_tool_names: list[str] | None = None,
) -> list[dict]:
    """Sanitize tool call inputs (convenience wrapper)."""
    return repair_tool_call_inputs(messages, allowed_tool_names).messages


def repair_tool_use_result_pairing(messages: list[dict]) -> ToolUseRepairReport:
    """Repair tool call / tool result pairing.

    - Moves matching tool results directly after their assistant turn
    - Inserts synthetic error results for missing IDs
    - Drops duplicate/orphan tool results
    """
    out: list[dict] = []
    added: list[dict] = []
    seen_ids: set[str] = set()
    dropped_duplicate = 0
    dropped_orphan = 0
    moved = False
    changed = False

    def push_tool_result(msg: dict) -> None:
        nonlocal dropped_duplicate, changed
        result_id = _extract_tool_result_id(msg)
        if result_id and result_id in seen_ids:
            dropped_duplicate += 1
            changed = True
            return
        if result_id:
            seen_ids.add(result_id)
        out.append(msg)

    i = 0
    while i < len(messages):
        msg = messages[i]
        if not isinstance(msg, dict):
            out.append(msg)
            i += 1
            continue

        role = msg.get("role")
        if role != "assistant":
            if role != "toolResult":
                out.append(msg)
            else:
                dropped_orphan += 1
                changed = True
            i += 1
            continue

        # Skip repair for aborted/errored messages
        stop_reason = msg.get("stopReason")
        if stop_reason in ("error", "aborted"):
            out.append(msg)
            i += 1
            continue

        tool_calls = _extract_tool_calls_from_assistant(msg)
        if not tool_calls:
            out.append(msg)
            i += 1
            continue

        call_ids = {tc["id"] for tc in tool_calls}
        call_names = {tc["id"]: tc["name"] for tc in tool_calls}

        span_results: dict[str, dict] = {}
        remainder: list[dict] = []

        j = i + 1
        while j < len(messages):
            next_msg = messages[j]
            if not isinstance(next_msg, dict):
                remainder.append(next_msg)
                j += 1
                continue

            next_role = next_msg.get("role")
            if next_role == "assistant":
                break

            if next_role == "toolResult":
                result_id = _extract_tool_result_id(next_msg)
                if result_id and result_id in call_ids:
                    if result_id in seen_ids:
                        dropped_duplicate += 1
                        changed = True
                    elif result_id not in span_results:
                        span_results[result_id] = next_msg
                    j += 1
                    continue
                # Orphan
                dropped_orphan += 1
                changed = True
                j += 1
                continue

            remainder.append(next_msg)
            j += 1

        out.append(msg)

        if span_results and remainder:
            moved = True
            changed = True

        for call in tool_calls:
            existing = span_results.get(call["id"])
            if existing:
                push_tool_result(existing)
            else:
                missing = make_missing_tool_result(call["id"], call["name"])
                added.append(missing)
                changed = True
                push_tool_result(missing)

        for rem in remainder:
            out.append(rem)

        i = j

    return ToolUseRepairReport(
        messages=out if (changed or moved) else messages,
        added=added,
        dropped_duplicate_count=dropped_duplicate,
        dropped_orphan_count=dropped_orphan,
        moved=changed or moved,
    )


def sanitize_tool_use_result_pairing(messages: list[dict]) -> list[dict]:
    """Sanitize tool use/result pairing (convenience wrapper)."""
    return repair_tool_use_result_pairing(messages).messages

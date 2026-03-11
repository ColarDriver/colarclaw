"""Session transcript repair — ported from bk/src/agents/session-transcript-repair.ts.

Repairs inconsistencies in session transcripts: repairs missing tool results,
handles duplicate/orphaned tool results, and sanitizes tool call inputs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("openclaw.agents.session_transcript_repair")

SYNTHETIC_ERROR_MESSAGE = "[Internal error: tool result was lost during session repair]"


@dataclass
class RepairResult:
    repaired: bool = False
    repairs_applied: list[str] | None = None
    original_length: int = 0
    final_length: int = 0


def repair_session_transcript(
    messages: list[dict[str, Any]],
    *,
    repair_tool_use_result_pairing: bool = True,
    sanitize_spawn_inputs: bool = True,
) -> RepairResult:
    """Repair common transcript inconsistencies.

    - Insert synthetic error results for tool calls missing their results.
    - Remove orphaned tool results whose corresponding calls are missing.
    - Deduplicate tool results.
    - Sanitize sensitive tool call inputs (like session_spawn credentials).
    """
    repairs: list[str] = []
    original_length = len(messages)

    if sanitize_spawn_inputs:
        count = _sanitize_spawn_inputs(messages)
        if count > 0:
            repairs.append(f"sanitized {count} spawn inputs")

    if repair_tool_use_result_pairing:
        missing = _repair_missing_tool_results(messages)
        if missing > 0:
            repairs.append(f"inserted {missing} synthetic tool results")

        orphaned = _remove_orphaned_tool_results(messages)
        if orphaned > 0:
            repairs.append(f"removed {orphaned} orphaned tool results")

        dupes = _deduplicate_tool_results(messages)
        if dupes > 0:
            repairs.append(f"removed {dupes} duplicate tool results")

    return RepairResult(
        repaired=len(repairs) > 0,
        repairs_applied=repairs if repairs else None,
        original_length=original_length,
        final_length=len(messages),
    )


def _get_tool_call_ids(message: dict[str, Any]) -> set[str]:
    """Extract tool call IDs from a message's tool_calls array."""
    ids: set[str] = set()
    tool_calls = message.get("tool_calls") or []
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            tc_id = tc.get("id") if isinstance(tc, dict) else None
            if tc_id:
                ids.add(tc_id)
    # Also check content blocks for tool_use type
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                block_id = block.get("id")
                if block_id:
                    ids.add(block_id)
    return ids


def _get_tool_result_ids(message: dict[str, Any]) -> set[str]:
    """Extract tool result IDs from a message."""
    ids: set[str] = set()
    # Direct tool_call_id on the message (OpenAI format)
    tc_id = message.get("tool_call_id")
    if tc_id:
        ids.add(tc_id)
    # content blocks with type=tool_result (Anthropic format)
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                block_id = block.get("tool_use_id")
                if block_id:
                    ids.add(block_id)
    return ids


def _repair_missing_tool_results(messages: list[dict[str, Any]]) -> int:
    """Insert synthetic error results for tool calls that have no matching results."""
    # Collect all tool result IDs present in the transcript
    all_result_ids: set[str] = set()
    for msg in messages:
        all_result_ids.update(_get_tool_result_ids(msg))

    # Find tool calls without matching results
    missing_count = 0
    insertions: list[tuple[int, dict[str, Any]]] = []
    for i, msg in enumerate(messages):
        call_ids = _get_tool_call_ids(msg)
        for call_id in call_ids:
            if call_id not in all_result_ids:
                synthetic = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": SYNTHETIC_ERROR_MESSAGE,
                }
                insertions.append((i + 1, synthetic))
                missing_count += 1

    # Insert in reverse to preserve indices
    for idx, msg in reversed(insertions):
        messages.insert(idx, msg)

    return missing_count


def _remove_orphaned_tool_results(messages: list[dict[str, Any]]) -> int:
    """Remove tool results whose corresponding tool calls don't exist."""
    all_call_ids: set[str] = set()
    for msg in messages:
        all_call_ids.update(_get_tool_call_ids(msg))

    orphaned_indices: list[int] = []
    for i, msg in enumerate(messages):
        result_ids = _get_tool_result_ids(msg)
        if result_ids and not result_ids.intersection(all_call_ids):
            orphaned_indices.append(i)

    for idx in reversed(orphaned_indices):
        messages.pop(idx)

    return len(orphaned_indices)


def _deduplicate_tool_results(messages: list[dict[str, Any]]) -> int:
    """Remove duplicate tool results (keep first occurrence)."""
    seen_result_ids: set[str] = set()
    duplicate_indices: list[int] = []

    for i, msg in enumerate(messages):
        result_ids = _get_tool_result_ids(msg)
        if not result_ids:
            continue
        all_seen = all(rid in seen_result_ids for rid in result_ids)
        if all_seen and result_ids:
            duplicate_indices.append(i)
        else:
            seen_result_ids.update(result_ids)

    for idx in reversed(duplicate_indices):
        messages.pop(idx)

    return len(duplicate_indices)


_SENSITIVE_SPAWN_FIELDS = {"api_key", "token", "secret", "password", "credential"}


def _sanitize_spawn_inputs(messages: list[dict[str, Any]]) -> int:
    """Redact sensitive fields in sessions_spawn tool call arguments."""
    count = 0
    for msg in messages:
        tool_calls = msg.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function", {})
            name = fn.get("name", "") if isinstance(fn, dict) else ""
            if name != "sessions_spawn":
                continue
            args = fn.get("arguments")
            if isinstance(args, str):
                # Try to parse and redact
                import json
                try:
                    parsed = json.loads(args)
                    if isinstance(parsed, dict):
                        changed = _redact_sensitive_fields(parsed)
                        if changed:
                            fn["arguments"] = json.dumps(parsed)
                            count += 1
                except (json.JSONDecodeError, Exception):
                    pass
            elif isinstance(args, dict):
                changed = _redact_sensitive_fields(args)
                if changed:
                    count += 1
    return count


def _redact_sensitive_fields(obj: dict[str, Any]) -> bool:
    """Redact fields with sensitive-looking names. Returns True if any fields were redacted."""
    changed = False
    for key in list(obj.keys()):
        lower_key = key.lower()
        if any(s in lower_key for s in _SENSITIVE_SPAWN_FIELDS):
            if obj[key] and isinstance(obj[key], str):
                obj[key] = "[REDACTED]"
                changed = True
        elif isinstance(obj[key], dict):
            if _redact_sensitive_fields(obj[key]):
                changed = True
    return changed

"""Tool call ID management — ported from bk/src/agents/tool-call-id.ts.

Sanitizes tool call IDs to be provider-compatible, extracts tool calls
from assistant messages, and provides transcript-wide ID rewriting.
"""
from __future__ import annotations
import hashlib
import re
import time
from typing import Any, Literal

ToolCallIdMode = Literal["strict", "strict9"]
STRICT9_LEN = 9
TOOL_CALL_TYPES = {"toolCall", "toolUse", "functionCall"}

def _short_hash(text: str, length: int = 8) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:length]

def sanitize_tool_call_id(id_value: str, mode: ToolCallIdMode = "strict") -> str:
    if not id_value or not isinstance(id_value, str):
        return "defaultid" if mode == "strict9" else "defaulttoolid"
    if mode == "strict9":
        alnum = re.sub(r"[^a-zA-Z0-9]", "", id_value)
        if len(alnum) >= STRICT9_LEN:
            return alnum[:STRICT9_LEN]
        if alnum:
            return _short_hash(alnum, STRICT9_LEN)
        return _short_hash("sanitized", STRICT9_LEN)
    alnum = re.sub(r"[^a-zA-Z0-9]", "", id_value)
    return alnum if alnum else "sanitizedtoolid"

def extract_tool_calls_from_assistant(msg: dict[str, Any]) -> list[dict[str, str]]:
    content = msg.get("content")
    if not isinstance(content, list):
        return []
    calls: list[dict[str, str]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        bid = block.get("id")
        btype = block.get("type")
        if isinstance(bid, str) and bid and isinstance(btype, str) and btype in TOOL_CALL_TYPES:
            name = block.get("name")
            calls.append({"id": bid, "name": name if isinstance(name, str) else ""})
    return calls

def extract_tool_result_id(msg: dict[str, Any]) -> str | None:
    for key in ("toolCallId", "toolUseId"):
        val = msg.get(key)
        if isinstance(val, str) and val:
            return val
    return None

def is_valid_tool_id(id_value: str, mode: ToolCallIdMode = "strict") -> bool:
    if not id_value or not isinstance(id_value, str):
        return False
    if mode == "strict9":
        return bool(re.match(r"^[a-zA-Z0-9]{9}$", id_value))
    return bool(re.match(r"^[a-zA-Z0-9]+$", id_value))

def _make_unique_tool_id(id_value: str, used: set[str], mode: ToolCallIdMode) -> str:
    MAX_LEN = 9 if mode == "strict9" else 40
    base = sanitize_tool_call_id(id_value, mode)[:MAX_LEN]
    if base and base not in used:
        return base
    for i in range(1000):
        hashed = _short_hash(f"{id_value}:{i}", MAX_LEN)
        if hashed not in used:
            return hashed
    return _short_hash(f"{id_value}:{time.time()}", MAX_LEN)

def _rewrite_assistant_tool_call_ids(msg: dict, resolve: Any) -> dict:
    content = msg.get("content")
    if not isinstance(content, list):
        return msg
    changed = False
    new_content = []
    for block in content:
        if not isinstance(block, dict):
            new_content.append(block)
            continue
        btype = block.get("type")
        bid = block.get("id")
        if btype in TOOL_CALL_TYPES and isinstance(bid, str) and bid:
            new_id = resolve(bid)
            if new_id != bid:
                changed = True
                new_content.append({**block, "id": new_id})
            else:
                new_content.append(block)
        else:
            new_content.append(block)
    return {**msg, "content": new_content} if changed else msg

def _rewrite_tool_result_ids(msg: dict, resolve: Any) -> dict:
    changed = False
    result = dict(msg)
    for key in ("toolCallId", "toolUseId"):
        val = msg.get(key)
        if isinstance(val, str) and val:
            new_val = resolve(val)
            if new_val != val:
                result[key] = new_val
                changed = True
    return result if changed else msg

def sanitize_tool_call_ids(messages: list[dict], mode: ToolCallIdMode = "strict") -> list[dict]:
    id_map: dict[str, str] = {}
    used: set[str] = set()
    def resolve(oid: str) -> str:
        if oid in id_map:
            return id_map[oid]
        new_id = _make_unique_tool_id(oid, used, mode)
        id_map[oid] = new_id
        used.add(new_id)
        return new_id
    changed = False
    out = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        role = msg.get("role")
        if role == "assistant":
            new_msg = _rewrite_assistant_tool_call_ids(msg, resolve)
            if new_msg is not msg:
                changed = True
            out.append(new_msg)
        elif role == "toolResult":
            new_msg = _rewrite_tool_result_ids(msg, resolve)
            if new_msg is not msg:
                changed = True
            out.append(new_msg)
        else:
            out.append(msg)
    return out if changed else messages

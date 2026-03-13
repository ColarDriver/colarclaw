"""ACP event mapper — ported from bk/src/acp/event-mapper.ts.

Extract text/attachments from ACP prompts and format tool metadata.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

ToolKind = Literal["read", "edit", "delete", "move", "search", "execute", "fetch", "other"]

INLINE_CONTROL_ESCAPE_MAP = {
    "\0": "\\0", "\r": "\\r", "\n": "\\n",
    "\t": "\\t", "\v": "\\v", "\f": "\\f",
    "\u2028": "\\u2028", "\u2029": "\\u2029",
}


@dataclass
class GatewayAttachment:
    type: str = ""
    mime_type: str = ""
    content: str = ""


def _escape_inline_control_chars(value: str) -> str:
    out: list[str] = []
    for ch in value:
        cp = ord(ch)
        is_control = cp <= 0x1F or (0x7F <= cp <= 0x9F) or cp in (0x2028, 0x2029)
        if not is_control:
            out.append(ch)
            continue
        mapped = INLINE_CONTROL_ESCAPE_MAP.get(ch)
        if mapped:
            out.append(mapped)
        elif cp <= 0xFF:
            out.append(f"\\x{cp:02x}")
        else:
            out.append(f"\\u{cp:04x}")
    return "".join(out)


def _escape_resource_title(value: str) -> str:
    escaped = _escape_inline_control_chars(value)
    return re.sub(r"[()[\]]", lambda m: f"\\{m.group()}", escaped)


def extract_text_from_prompt(prompt: list[dict[str, Any]], max_bytes: int | None = None) -> str:
    parts: list[str] = []
    total_bytes = 0
    for block in prompt:
        btype = block.get("type", "")
        block_text: str | None = None
        if btype == "text":
            block_text = block.get("text")
        elif btype == "resource":
            resource = block.get("resource")
            if isinstance(resource, dict) and resource.get("text"):
                block_text = resource["text"]
        elif btype == "resource_link":
            title = f" ({_escape_resource_title(block['title'])})" if block.get("title") else ""
            uri = _escape_inline_control_chars(block.get("uri", "")) if block.get("uri") else ""
            block_text = f"[Resource link{title}] {uri}" if uri else f"[Resource link{title}]"
        if block_text is not None:
            if max_bytes is not None:
                sep = 1 if parts else 0
                total_bytes += sep + len(block_text.encode("utf-8"))
                if total_bytes > max_bytes:
                    raise ValueError(f"Prompt exceeds maximum allowed size of {max_bytes} bytes")
            parts.append(block_text)
    return "\n".join(parts)


def extract_attachments_from_prompt(prompt: list[dict[str, Any]]) -> list[GatewayAttachment]:
    attachments: list[GatewayAttachment] = []
    for block in prompt:
        if block.get("type") != "image":
            continue
        data = block.get("data")
        mime = block.get("mimeType") or block.get("mime_type")
        if data and mime:
            attachments.append(GatewayAttachment(type="image", mime_type=mime, content=data))
    return attachments


def format_tool_title(name: str | None, args: dict[str, Any] | None = None) -> str:
    base = name or "tool"
    if not args:
        return base
    parts = []
    for key, value in args.items():
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        safe = raw[:100] + "..." if len(raw) > 100 else raw
        parts.append(f"{key}: {safe}")
    return f"{base}: {', '.join(parts)}"


def infer_tool_kind(name: str | None = None) -> ToolKind:
    if not name:
        return "other"
    n = name.lower()
    if "read" in n:
        return "read"
    if "write" in n or "edit" in n:
        return "edit"
    if "delete" in n or "remove" in n:
        return "delete"
    if "move" in n or "rename" in n:
        return "move"
    if "search" in n or "find" in n:
        return "search"
    if "exec" in n or "run" in n or "bash" in n:
        return "execute"
    if "fetch" in n or "http" in n:
        return "fetch"
    return "other"

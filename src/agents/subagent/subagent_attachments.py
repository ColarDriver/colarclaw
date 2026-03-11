"""Subagent attachments — ported from bk/src/agents/subagent-attachments.ts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SubagentAttachment:
    name: str
    content: str
    mime_type: str = "text/plain"
    size: int = 0

def collect_subagent_attachments(message: dict[str, Any]) -> list[SubagentAttachment]:
    raw = message.get("attachments")
    if not isinstance(raw, list):
        return []
    attachments: list[SubagentAttachment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        content = item.get("content", "")
        if name and content:
            attachments.append(SubagentAttachment(
                name=name, content=content,
                mime_type=item.get("mimeType", "text/plain"),
                size=len(content),
            ))
    return attachments

def serialize_attachments(attachments: list[SubagentAttachment]) -> list[dict[str, Any]]:
    return [{"name": a.name, "content": a.content, "mimeType": a.mime_type} for a in attachments]

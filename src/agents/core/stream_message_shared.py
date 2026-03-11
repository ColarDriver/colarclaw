"""Stream message shared — ported from bk/src/agents/stream-message-shared.ts."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Literal

StreamEventType = Literal[
    "text_delta", "tool_call_start", "tool_call_delta", "tool_call_end",
    "thinking_delta", "message_start", "message_end", "error",
]

@dataclass
class StreamEvent:
    type: StreamEventType
    data: Any = None
    timestamp: float = field(default_factory=time.time)

@dataclass
class StreamTextDelta:
    text: str
    index: int = 0

@dataclass
class StreamToolCallStart:
    tool_call_id: str
    name: str

@dataclass
class StreamToolCallDelta:
    tool_call_id: str
    input_delta: str

def create_text_delta(text: str, index: int = 0) -> StreamEvent:
    return StreamEvent(type="text_delta", data=StreamTextDelta(text=text, index=index))

def create_tool_call_start(tool_call_id: str, name: str) -> StreamEvent:
    return StreamEvent(type="tool_call_start", data=StreamToolCallStart(tool_call_id=tool_call_id, name=name))

def create_error_event(error: str) -> StreamEvent:
    return StreamEvent(type="error", data={"error": error})

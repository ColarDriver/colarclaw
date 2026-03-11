"""Usage tracking — ported from bk/src/agents/usage.ts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0

@dataclass
class RunUsage:
    model: str = ""
    provider: str = ""
    tokens: TokenUsage = field(default_factory=TokenUsage)
    api_calls: int = 0
    tool_calls: int = 0
    duration_ms: float = 0

def merge_token_usage(a: TokenUsage, b: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        cache_read_tokens=a.cache_read_tokens + b.cache_read_tokens,
        cache_write_tokens=a.cache_write_tokens + b.cache_write_tokens,
        total_tokens=a.total_tokens + b.total_tokens,
    )

def parse_usage_from_response(response: dict[str, Any]) -> TokenUsage:
    usage = response.get("usage", {})
    return TokenUsage(
        input_tokens=usage.get("input_tokens", usage.get("prompt_tokens", 0)),
        output_tokens=usage.get("output_tokens", usage.get("completion_tokens", 0)),
        cache_read_tokens=usage.get("cache_read_input_tokens", usage.get("cache_read_tokens", 0)),
        cache_write_tokens=usage.get("cache_creation_input_tokens", usage.get("cache_write_tokens", 0)),
        total_tokens=usage.get("total_tokens", 0),
    )

def format_usage_summary(usage: TokenUsage) -> str:
    parts = [f"in={usage.input_tokens}", f"out={usage.output_tokens}"]
    if usage.cache_read_tokens:
        parts.append(f"cache_read={usage.cache_read_tokens}")
    if usage.cache_write_tokens:
        parts.append(f"cache_write={usage.cache_write_tokens}")
    return ", ".join(parts)

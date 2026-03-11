"""Model alias — ported from bk/src/agents/model-alias.ts.

Resolves model aliases to canonical model identifiers.
"""
from __future__ import annotations

from typing import Any

# Common model aliases
_BUILTIN_ALIASES: dict[str, str] = {
    "gpt4": "gpt-4",
    "gpt4o": "gpt-4o",
    "gpt4o-mini": "gpt-4o-mini",
    "gpt-4-turbo": "gpt-4-turbo",
    "claude": "claude-sonnet-4-5-20250514",
    "claude-opus": "claude-opus-4-0-20250514",
    "claude-sonnet": "claude-sonnet-4-5-20250514",
    "claude-haiku": "claude-3-5-haiku-20241022",
    "sonnet": "claude-sonnet-4-5-20250514",
    "opus": "claude-opus-4-0-20250514",
    "haiku": "claude-3-5-haiku-20241022",
    "gemini": "gemini-2.5-pro",
    "gemini-pro": "gemini-2.5-pro",
    "gemini-flash": "gemini-2.5-flash",
    "deepseek": "deepseek-chat",
    "deepseek-coder": "deepseek-coder",
    "o1": "o1",
    "o1-mini": "o1-mini",
    "o1-preview": "o1-preview",
    "o3": "o3",
    "o3-mini": "o3-mini",
    "o4-mini": "o4-mini",
}


def resolve_model_alias(
    model_id: str,
    custom_aliases: dict[str, str] | None = None,
) -> str:
    """Resolve a model alias to its canonical ID.

    Custom aliases take precedence over built-in aliases.
    """
    if not model_id:
        return model_id
    normalized = model_id.strip().lower()
    if custom_aliases:
        resolved = custom_aliases.get(normalized)
        if resolved:
            return resolved
    return _BUILTIN_ALIASES.get(normalized, model_id)


def list_model_aliases(custom_aliases: dict[str, str] | None = None) -> dict[str, str]:
    """Return the complete alias map (built-in merged with custom)."""
    result = dict(_BUILTIN_ALIASES)
    if custom_aliases:
        result.update(custom_aliases)
    return result

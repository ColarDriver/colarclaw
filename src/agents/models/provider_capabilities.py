"""Provider capabilities — ported from bk/src/agents/provider-capabilities.ts.

Maps provider IDs to capability flags that influence how tool schemas,
thinking signatures, and turn validation are handled.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agents.model_selection import normalize_provider_id


@dataclass(frozen=True)
class ProviderCapabilities:
    anthropic_tool_schema_mode: Literal["native", "openai-functions"] = "native"
    anthropic_tool_choice_mode: Literal["native", "openai-string-modes"] = "native"
    preserve_anthropic_thinking_signatures: bool = True
    openai_compat_turn_validation: bool = True
    gemini_thought_signature_sanitization: bool = False
    transcript_tool_call_id_mode: Literal["default", "strict9"] = "default"


_DEFAULT = ProviderCapabilities()

_PROVIDER_CAPABILITIES: dict[str, dict[str, object]] = {
    "kimi-coding": {
        "anthropic_tool_schema_mode": "openai-functions",
        "anthropic_tool_choice_mode": "openai-string-modes",
        "preserve_anthropic_thinking_signatures": False,
    },
    "mistral": {
        "transcript_tool_call_id_mode": "strict9",
    },
    "openrouter": {
        "openai_compat_turn_validation": False,
        "gemini_thought_signature_sanitization": True,
    },
    "opencode": {
        "openai_compat_turn_validation": False,
        "gemini_thought_signature_sanitization": True,
    },
    "kilocode": {
        "gemini_thought_signature_sanitization": True,
    },
}


def resolve_provider_capabilities(provider: str | None = None) -> ProviderCapabilities:
    """Get capability flags for a provider."""
    normalized = normalize_provider_id(provider or "")
    overrides = _PROVIDER_CAPABILITIES.get(normalized, {})
    if not overrides:
        return _DEFAULT
    # Merge overrides into a new ProviderCapabilities
    fields = {
        "anthropic_tool_schema_mode": overrides.get("anthropic_tool_schema_mode", _DEFAULT.anthropic_tool_schema_mode),
        "anthropic_tool_choice_mode": overrides.get("anthropic_tool_choice_mode", _DEFAULT.anthropic_tool_choice_mode),
        "preserve_anthropic_thinking_signatures": overrides.get("preserve_anthropic_thinking_signatures", _DEFAULT.preserve_anthropic_thinking_signatures),
        "openai_compat_turn_validation": overrides.get("openai_compat_turn_validation", _DEFAULT.openai_compat_turn_validation),
        "gemini_thought_signature_sanitization": overrides.get("gemini_thought_signature_sanitization", _DEFAULT.gemini_thought_signature_sanitization),
        "transcript_tool_call_id_mode": overrides.get("transcript_tool_call_id_mode", _DEFAULT.transcript_tool_call_id_mode),
    }
    return ProviderCapabilities(**fields)  # type: ignore[arg-type]


# ── Convenience helpers ───────────────────────────────────────────────────

def preserves_anthropic_thinking_signatures(provider: str | None = None) -> bool:
    return resolve_provider_capabilities(provider).preserve_anthropic_thinking_signatures


def requires_openai_compatible_anthropic_tool_payload(provider: str | None = None) -> bool:
    caps = resolve_provider_capabilities(provider)
    return (
        caps.anthropic_tool_schema_mode != "native"
        or caps.anthropic_tool_choice_mode != "native"
    )


def uses_openai_function_anthropic_tool_schema(provider: str | None = None) -> bool:
    return resolve_provider_capabilities(provider).anthropic_tool_schema_mode == "openai-functions"


def uses_openai_string_mode_anthropic_tool_choice(provider: str | None = None) -> bool:
    return resolve_provider_capabilities(provider).anthropic_tool_choice_mode == "openai-string-modes"


def supports_openai_compat_turn_validation(provider: str | None = None) -> bool:
    return resolve_provider_capabilities(provider).openai_compat_turn_validation


def sanitizes_gemini_thought_signatures(provider: str | None = None) -> bool:
    return resolve_provider_capabilities(provider).gemini_thought_signature_sanitization


def resolve_transcript_tool_call_id_mode(
    provider: str | None = None,
) -> Literal["strict9"] | None:
    mode = resolve_provider_capabilities(provider).transcript_tool_call_id_mode
    return mode if mode == "strict9" else None

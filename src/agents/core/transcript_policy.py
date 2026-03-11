"""Transcript policy — ported from bk/src/agents/transcript-policy.ts.

Resolves transcript sanitization policies based on provider, model API,
and model ID to determine how session history should be cleaned before
sending to LLM providers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .model_selection import normalize_provider_id
from .provider_capabilities import (
    preserves_anthropic_thinking_signatures,
    resolve_transcript_tool_call_id_mode,
    sanitizes_gemini_thought_signatures,
    supports_openai_compat_turn_validation,
)

TranscriptSanitizeMode = Literal["full", "images-only"]


@dataclass
class ThoughtSignatureSanitizeConfig:
    allow_base64_only: bool = False
    include_camel_case: bool = False


@dataclass
class TranscriptPolicy:
    sanitize_mode: TranscriptSanitizeMode = "images-only"
    sanitize_tool_call_ids: bool = False
    tool_call_id_mode: str | None = None
    repair_tool_use_result_pairing: bool = True
    preserve_signatures: bool = False
    sanitize_thought_signatures: ThoughtSignatureSanitizeConfig | None = None
    sanitize_thinking_signatures: bool = False
    drop_thinking_blocks: bool = False
    apply_google_turn_ordering: bool = False
    validate_gemini_turns: bool = False
    validate_anthropic_turns: bool = False
    allow_synthetic_tool_results: bool = False


_MISTRAL_MODEL_HINTS = [
    "mistral", "mixtral", "codestral", "pixtral",
    "devstral", "ministral", "mistralai",
]
_OPENAI_MODEL_APIS = {"openai", "openai-completions", "openai-responses", "openai-codex-responses"}
_OPENAI_PROVIDERS = {"openai", "openai-codex"}


def _is_openai_api(model_api: str | None) -> bool:
    return bool(model_api and model_api in _OPENAI_MODEL_APIS)


def _is_openai_provider(provider: str | None) -> bool:
    return bool(provider and provider in _OPENAI_PROVIDERS)


def _is_anthropic_api(model_api: str | None, provider: str | None) -> bool:
    if model_api in ("anthropic-messages", "bedrock-converse-stream"):
        return True
    normalized = normalize_provider_id(provider or "")
    return normalized in ("anthropic", "amazon-bedrock")


def _is_mistral_model(model_id: str | None) -> bool:
    normalized = (model_id or "").lower()
    if not normalized:
        return False
    return any(hint in normalized for hint in _MISTRAL_MODEL_HINTS)


def _should_sanitize_gemini_thought_signatures(
    provider: str | None,
    model_id: str | None,
) -> bool:
    if not sanitizes_gemini_thought_signatures(provider):
        return False
    lower = (model_id or "").lower()
    return bool(lower and "gemini" in lower)


def _is_google_model_api(model_api: str | None) -> bool:
    """Check if model API is Google-based."""
    return model_api in ("google-genai", "vertex-ai")


def resolve_transcript_policy(
    model_api: str | None = None,
    provider: str | None = None,
    model_id: str | None = None,
) -> TranscriptPolicy:
    """Resolve transcript policy for a given provider/model combination."""
    norm_provider = normalize_provider_id(provider or "")
    is_google = _is_google_model_api(model_api)
    is_anthropic = _is_anthropic_api(model_api, norm_provider)
    is_openai = _is_openai_provider(norm_provider) or (not norm_provider and _is_openai_api(model_api))

    is_strict_openai_compat = (
        model_api == "openai-completions"
        and not is_openai
        and supports_openai_compat_turn_validation(norm_provider)
    )

    provider_tool_call_id_mode = resolve_transcript_tool_call_id_mode(norm_provider)
    is_mistral = provider_tool_call_id_mode == "strict9" or _is_mistral_model(model_id)
    should_sanitize_gemini = _should_sanitize_gemini_thought_signatures(norm_provider, model_id)

    is_copilot_claude = norm_provider == "github-copilot" and "claude" in (model_id or "").lower()
    requires_openai_compat_tool_id = model_api == "openai-completions"

    drop_thinking_blocks = is_copilot_claude
    needs_non_image_sanitize = is_google or is_anthropic or is_mistral or should_sanitize_gemini

    sanitize_tool_call_ids = is_google or is_mistral or is_anthropic or requires_openai_compat_tool_id
    tool_call_id_mode: str | None = (
        provider_tool_call_id_mode if provider_tool_call_id_mode
        else "strict9" if is_mistral
        else "strict" if sanitize_tool_call_ids
        else None
    )

    sanitize_thought_signatures = (
        ThoughtSignatureSanitizeConfig(allow_base64_only=True, include_camel_case=True)
        if (should_sanitize_gemini or is_google) else None
    )

    return TranscriptPolicy(
        sanitize_mode="images-only" if is_openai else ("full" if needs_non_image_sanitize else "images-only"),
        sanitize_tool_call_ids=(not is_openai and sanitize_tool_call_ids) or requires_openai_compat_tool_id,
        tool_call_id_mode=tool_call_id_mode,
        repair_tool_use_result_pairing=True,
        preserve_signatures=is_anthropic and preserves_anthropic_thinking_signatures(norm_provider),
        sanitize_thought_signatures=None if is_openai else sanitize_thought_signatures,
        sanitize_thinking_signatures=False,
        drop_thinking_blocks=drop_thinking_blocks,
        apply_google_turn_ordering=not is_openai and (is_google or is_strict_openai_compat),
        validate_gemini_turns=not is_openai and (is_google or is_strict_openai_compat),
        validate_anthropic_turns=not is_openai and (is_anthropic or is_strict_openai_compat),
        allow_synthetic_tool_results=not is_openai and (is_google or is_anthropic),
    )

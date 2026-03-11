"""Model selection and normalization.

Ported from bk/src/agents/model-selection.ts
Handles parsing provider/model keys, provider normalization, alias resolution,
and allowed-model-set building.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-5"

# Anthropic short aliases  (matches TS ANTHROPIC_MODEL_ALIASES)
_ANTHROPIC_ALIASES: dict[str, str] = {
    "opus-4.6": "claude-opus-4-6",
    "opus-4.5": "claude-opus-4-5",
    "sonnet-4.6": "claude-sonnet-4-6",
    "sonnet-4.5": "claude-sonnet-4-5",
}


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass
class ModelAliasEntry:
    alias: str
    ref: ModelRef


@dataclass
class ModelAliasIndex:
    by_alias: dict[str, ModelAliasEntry] = field(default_factory=dict)
    by_key: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider ID normalisation
# ---------------------------------------------------------------------------

def normalize_provider_id(provider: str) -> str:
    """Normalise provider strings to canonical lower-case forms."""
    normalized = provider.strip().lower()
    _aliases = {
        "z.ai": "zai",
        "z-ai": "zai",
        "opencode-zen": "opencode",
        "qwen": "qwen-portal",
        "kimi-code": "kimi-coding",
        "bedrock": "amazon-bedrock",
        "aws-bedrock": "amazon-bedrock",
        "bytedance": "volcengine",
        "doubao": "volcengine",
    }
    return _aliases.get(normalized, normalized)


def normalize_provider_id_for_auth(provider: str) -> str:
    normalized = normalize_provider_id(provider)
    if normalized == "volcengine-plan":
        return "volcengine"
    if normalized == "byteplus-plan":
        return "byteplus"
    return normalized


# ---------------------------------------------------------------------------
# Model ID normalisation (provider-specific)
# ---------------------------------------------------------------------------

def _normalize_anthropic_model_id(model: str) -> str:
    trimmed = model.strip()
    return _ANTHROPIC_ALIASES.get(trimmed.lower(), trimmed)


def _normalize_google_model_id(model: str) -> str:
    """Normalise Gemini model IDs (mirrors normalizeGoogleModelId in TS)."""
    trimmed = model.strip()
    # gemini-1.5-pro-latest → gemini-1.5-pro, etc.
    if trimmed.endswith("-latest"):
        trimmed = trimmed[: -len("-latest")]
    return trimmed


def _normalize_provider_model_id(provider: str, model: str) -> str:
    if provider == "anthropic":
        return _normalize_anthropic_model_id(model)
    if provider == "google":
        return _normalize_google_model_id(model)
    if provider == "openrouter" and "/" not in model:
        return f"openrouter/{model}"
    if provider == "vercel-ai-gateway" and "/" not in model:
        normalized = _normalize_anthropic_model_id(model)
        if normalized.startswith("claude-"):
            return f"anthropic/{normalized}"
    return model


def normalize_model_ref(provider: str, model: str) -> ModelRef:
    normalized_provider = normalize_provider_id(provider)
    normalized_model = _normalize_provider_model_id(normalized_provider, model.strip())
    return ModelRef(provider=normalized_provider, model=normalized_model)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_model_ref(raw: str, default_provider: str) -> ModelRef | None:
    trimmed = raw.strip()
    if not trimmed:
        return None
    slash = trimmed.find("/")
    if slash == -1:
        return normalize_model_ref(default_provider, trimmed)
    provider_raw = trimmed[:slash].strip()
    model_raw = trimmed[slash + 1:].strip()
    if not provider_raw or not model_raw:
        return None
    return normalize_model_ref(provider_raw, model_raw)


def model_key(provider: str, model: str) -> str:
    return f"{provider}/{model}"


# ---------------------------------------------------------------------------
# Alias index
# ---------------------------------------------------------------------------

def build_model_alias_index(
    *,
    model_registry: list[str],
    default_provider: str,
) -> ModelAliasIndex:
    """Build alias lookup from model registry entries.

    Registry format: ``provider/model-id=Alias Name``
    """
    index = ModelAliasIndex()
    for raw in model_registry:
        value = raw.strip()
        if not value:
            continue
        alias = ""
        if "=" in value:
            left, right = value.split("=", 1)
            value = left.strip()
            alias = right.strip()
        ref = parse_model_ref(value, default_provider)
        if ref is None or not alias:
            continue
        alias_key = alias.strip().lower()
        entry = ModelAliasEntry(alias=alias, ref=ref)
        index.by_alias[alias_key] = entry
        key = model_key(ref.provider, ref.model)
        index.by_key.setdefault(key, []).append(alias)
    return index


# ---------------------------------------------------------------------------
# Model ref resolution (with alias support)
# ---------------------------------------------------------------------------

def resolve_model_ref_from_string(
    *,
    raw: str,
    default_provider: str,
    alias_index: ModelAliasIndex | None = None,
) -> ModelRef | None:
    model_part = raw.strip()
    if not model_part:
        return None
    # Try alias first (only for short names without slash)
    if "/" not in model_part and alias_index:
        alias_key = model_part.lower()
        entry = alias_index.by_alias.get(alias_key)
        if entry:
            return entry.ref
    return parse_model_ref(model_part, default_provider)


# ---------------------------------------------------------------------------
# Allowlist helpers
# ---------------------------------------------------------------------------

def build_allowlist_keys(
    *,
    model_registry: list[str],
    default_provider: str,
) -> set[str] | None:
    """Return the set of allowed model keys from registry, or None if empty (allow any)."""
    keys: set[str] = set()
    for raw in model_registry:
        ref = parse_model_ref(raw.split("=")[0].strip(), default_provider)
        if ref:
            keys.add(ref.key)
    return keys if keys else None


# ---------------------------------------------------------------------------
# Resolve configured model (from settings / config)
# ---------------------------------------------------------------------------

def resolve_configured_model_ref(
    *,
    default_model_str: str,
    default_provider: str = DEFAULT_PROVIDER,
    default_model: str = DEFAULT_MODEL,
    alias_index: ModelAliasIndex | None = None,
) -> ModelRef:
    """Parse and return a ModelRef from a raw 'provider/model' string."""
    trimmed = default_model_str.strip()
    if not trimmed:
        return ModelRef(provider=default_provider, model=default_model)

    ref = resolve_model_ref_from_string(
        raw=trimmed,
        default_provider=default_provider,
        alias_index=alias_index,
    )
    if ref:
        return ref

    return ModelRef(provider=default_provider, model=default_model)


# ---------------------------------------------------------------------------
# Provider detection helpers (for LLM dispatch)
# ---------------------------------------------------------------------------

_OPENAI_COMPAT_PROVIDERS = {
    "openai", "azure", "openrouter", "anyscale",
    "perplexity", "together", "groq", "fireworks",
    "nvidia", "vercel-ai-gateway", "cloudflare-ai-gateway",
    "volcengine", "byteplus", "doubao", "kimi-coding",
    "huggingface", "opencode", "zai", "qwen-portal",
}

_ANTHROPIC_PROVIDERS = {"anthropic", "amazon-bedrock"}
_GOOGLE_PROVIDERS = {"google", "gemini"}
_OLLAMA_PROVIDERS = {"ollama"}


def is_openai_compat(provider: str) -> bool:
    return normalize_provider_id(provider) in _OPENAI_COMPAT_PROVIDERS


def is_anthropic(provider: str) -> bool:
    return normalize_provider_id(provider) in _ANTHROPIC_PROVIDERS


def is_google(provider: str) -> bool:
    return normalize_provider_id(provider) in _GOOGLE_PROVIDERS


def is_ollama(provider: str) -> bool:
    return normalize_provider_id(provider) in _OLLAMA_PROVIDERS

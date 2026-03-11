"""Models config providers shard.

Ported subset from ``bk/src/agents/models-config.providers.ts`` for Python.
Provides provider-key normalization, env helpers, Ollama/vLLM discovery,
and shared provider config interfaces used by merge logic.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from typing import TypedDict

from agents.model_auth import PROVIDER_ENV_VARS

log = logging.getLogger("openclaw.agents.models_config_providers")

MINIMAX_OAUTH_MARKER = "minimax-oauth"
QWEN_OAUTH_MARKER = "qwen-oauth"
OLLAMA_LOCAL_AUTH_MARKER = "ollama-local"
NON_ENV_SECRETREF_MARKER = "secretref-managed"

AWS_BEARER_TOKEN_BEDROCK = "AWS_BEARER_TOKEN_BEDROCK"
AWS_ACCESS_KEY_ID = "AWS_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY = "AWS_SECRET_ACCESS_KEY"
AWS_PROFILE = "AWS_PROFILE"

OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"
VLLM_DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
DISCOVERY_DEFAULT_CONTEXT_WINDOW = 128_000
DISCOVERY_DEFAULT_MAX_TOKENS = 8_192
DISCOVERY_DEFAULT_COST = {
    "input": 0,
    "output": 0,
    "cacheRead": 0,
    "cacheWrite": 0,
}

_ENV_VAR_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

_PROVIDER_KEY_ALIASES = {
    "bedrock": "amazon-bedrock",
    "aws-bedrock": "amazon-bedrock",
    "qwen": "qwen-portal",
    "kimi-code": "kimi-coding",
    "z.ai": "zai",
    "z-ai": "zai",
    "opencode-zen": "opencode",
    "bytedance": "volcengine",
    "doubao": "volcengine",
}


class ProviderModelConfig(TypedDict, total=False):
    """Provider model config entry (subset used by Python migration shards)."""

    id: str
    name: str
    api: str
    reasoning: bool
    input: list[str]
    cost: dict[str, float | int]
    contextWindow: int
    maxTokens: int


class ProviderConfig(TypedDict, total=False):
    """Provider config entry used by models.json-like config maps."""

    apiKey: str
    baseUrl: str
    api: str
    auth: str
    authHeader: bool
    headers: dict[str, str]
    models: list[ProviderModelConfig]


class ExistingProviderConfig(ProviderConfig, total=False):
    """Provider config with persisted secret fields used for merge preservation."""


ProviderConfigMap = dict[str, ProviderConfig]


def normalize_provider_key(provider_key: str) -> str:
    """Normalize provider keys to a canonical config key."""
    normalized = provider_key.strip().lower()
    return _PROVIDER_KEY_ALIASES.get(normalized, normalized)


def normalize_api_key_config(value: str) -> str:
    """Normalize config apiKey value, unwrapping `${ENV}` syntax when present."""
    trimmed = value.strip()
    match = re.fullmatch(r"\$\{([A-Z0-9_]+)\}", trimmed)
    return match.group(1) if match else trimmed


def list_known_provider_env_api_key_names() -> set[str]:
    """Return known env var names that can legitimately appear as apiKey markers."""
    names: set[str] = {
        AWS_BEARER_TOKEN_BEDROCK,
        AWS_ACCESS_KEY_ID,
        AWS_PROFILE,
    }
    for candidates in PROVIDER_ENV_VARS.values():
        for env_var in candidates:
            if env_var and isinstance(env_var, str):
                names.add(env_var.strip())
    return {name for name in names if name}


def is_non_secret_api_key_marker(value: str, *, include_env_var_name: bool = True) -> bool:
    """Check whether an apiKey value is a non-secret marker, not plaintext secret."""
    trimmed = value.strip()
    if not trimmed:
        return False
    if trimmed in {
        MINIMAX_OAUTH_MARKER,
        QWEN_OAUTH_MARKER,
        OLLAMA_LOCAL_AUTH_MARKER,
        NON_ENV_SECRETREF_MARKER,
        AWS_BEARER_TOKEN_BEDROCK,
        AWS_ACCESS_KEY_ID,
        AWS_PROFILE,
    }:
        return True
    if not include_env_var_name:
        return False
    return trimmed in list_known_provider_env_api_key_names()


def provider_env_api_key_candidates(provider: str) -> list[str]:
    """Return ordered env var candidates for provider API key lookup."""
    normalized = normalize_provider_key(provider)
    candidates = list(PROVIDER_ENV_VARS.get(normalized, ()))
    fallback = f"{normalized.upper().replace('-', '_')}_API_KEY"
    if fallback not in candidates:
        candidates.append(fallback)
    return [c for c in candidates if c and isinstance(c, str)]


def resolve_env_api_key_var_name(
    provider: str,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve provider env var name that currently has a non-empty value."""
    env_map = env or os.environ
    for env_var in provider_env_api_key_candidates(provider):
        value = str(env_map.get(env_var, "")).strip()
        if value:
            return env_var
    return None


def resolve_aws_sdk_api_key_var_name(env: Mapping[str, str] | None = None) -> str:
    """Resolve AWS auth env marker used for Bedrock-style auth mode."""
    env_map = env or os.environ
    if str(env_map.get(AWS_BEARER_TOKEN_BEDROCK, "")).strip():
        return AWS_BEARER_TOKEN_BEDROCK
    if str(env_map.get(AWS_ACCESS_KEY_ID, "")).strip() and str(
        env_map.get(AWS_SECRET_ACCESS_KEY, "")
    ).strip():
        return AWS_ACCESS_KEY_ID
    if str(env_map.get(AWS_PROFILE, "")).strip():
        return AWS_PROFILE
    return AWS_PROFILE


def resolve_ollama_api_base(configured_base_url: str | None = None) -> str:
    """Resolve Ollama native API base, stripping trailing slash and `/v1` suffix."""
    if not configured_base_url or not configured_base_url.strip():
        return OLLAMA_DEFAULT_BASE_URL
    trimmed = configured_base_url.strip().rstrip("/")
    return re.sub(r"/v1$", "", trimmed, flags=re.IGNORECASE)


def _is_reasoning_model(model_id: str) -> bool:
    lower = model_id.lower()
    return "r1" in lower or "reasoning" in lower or "think" in lower


def discover_ollama_models(
    base_url: str | None = None,
    *,
    timeout_s: float = 5.0,
    quiet: bool = False,
    max_models: int = 200,
) -> list[ProviderModelConfig]:
    """Discover Ollama models from `/api/tags` (lightweight, no `/api/show` fanout)."""
    api_base = resolve_ollama_api_base(base_url)
    try:
        import httpx

        response = httpx.get(f"{api_base}/api/tags", timeout=timeout_s)
        if response.status_code < 200 or response.status_code >= 300:
            if not quiet:
                log.warning("Failed to discover Ollama models: %s", response.status_code)
            return []

        payload = response.json()
        models_raw = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models_raw, list):
            return []

        discovered: list[ProviderModelConfig] = []
        for model in models_raw[:max_models]:
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("name", "")).strip()
            if not model_id:
                continue
            discovered.append(
                {
                    "id": model_id,
                    "name": model_id,
                    "reasoning": _is_reasoning_model(model_id),
                    "input": ["text"],
                    "cost": dict(DISCOVERY_DEFAULT_COST),
                    "contextWindow": DISCOVERY_DEFAULT_CONTEXT_WINDOW,
                    "maxTokens": DISCOVERY_DEFAULT_MAX_TOKENS,
                }
            )
        return discovered
    except Exception as exc:
        if not quiet:
            log.warning("Failed to discover Ollama models: %s", exc)
        return []


def discover_vllm_models(
    base_url: str | None = None,
    *,
    api_key: str | None = None,
    timeout_s: float = 5.0,
    quiet: bool = False,
) -> list[ProviderModelConfig]:
    """Discover vLLM models from OpenAI-compatible `/models` endpoint."""
    resolved_base_url = (base_url or VLLM_DEFAULT_BASE_URL).strip().rstrip("/")
    if not resolved_base_url:
        resolved_base_url = VLLM_DEFAULT_BASE_URL
    url = f"{resolved_base_url}/models"
    headers: dict[str, str] | None = None
    if api_key and api_key.strip():
        headers = {"Authorization": f"Bearer {api_key.strip()}"}

    try:
        import httpx

        response = httpx.get(url, headers=headers, timeout=timeout_s)
        if response.status_code < 200 or response.status_code >= 300:
            if not quiet:
                log.warning("Failed to discover vLLM models: %s", response.status_code)
            return []

        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []

        discovered: list[ProviderModelConfig] = []
        for model in data:
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("id", "")).strip()
            if not model_id:
                continue
            discovered.append(
                {
                    "id": model_id,
                    "name": model_id,
                    "reasoning": _is_reasoning_model(model_id),
                    "input": ["text"],
                    "cost": dict(DISCOVERY_DEFAULT_COST),
                    "contextWindow": DISCOVERY_DEFAULT_CONTEXT_WINDOW,
                    "maxTokens": DISCOVERY_DEFAULT_MAX_TOKENS,
                }
            )
        return discovered
    except Exception as exc:
        if not quiet:
            log.warning("Failed to discover vLLM models: %s", exc)
        return []


def normalize_providers(providers: Mapping[str, ProviderConfig] | None) -> ProviderConfigMap:
    """Normalize provider map keys and apiKey format while preserving values."""
    if not providers:
        return {}

    out: ProviderConfigMap = {}
    for key, provider in providers.items():
        normalized_key = normalize_provider_key(str(key))
        if not normalized_key:
            continue

        next_provider: ProviderConfig = dict(provider or {})  # shallow copy
        api_key = next_provider.get("apiKey")
        if isinstance(api_key, str):
            normalized_api_key = normalize_api_key_config(api_key)
            next_provider["apiKey"] = normalized_api_key
            if normalized_api_key and not _ENV_VAR_NAME_RE.match(normalized_api_key):
                # Keep plaintext or marker values untouched after basic normalization.
                pass

        existing = out.get(normalized_key)
        if existing:
            merged: ProviderConfig = dict(existing)
            merged.update(next_provider)
            if "models" in next_provider:
                merged["models"] = next_provider["models"]
            out[normalized_key] = merged
        else:
            out[normalized_key] = next_provider

    return out


def build_ollama_provider(
    configured_base_url: str | None = None,
    *,
    quiet: bool = False,
) -> ProviderConfig:
    """Build an Ollama provider config with lightweight discovered models."""
    models = discover_ollama_models(configured_base_url, quiet=quiet)
    return {
        "baseUrl": resolve_ollama_api_base(configured_base_url),
        "api": "ollama",
        "models": models,
    }


def build_vllm_provider(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    quiet: bool = False,
) -> ProviderConfig:
    """Build a vLLM provider config with lightweight discovered models."""
    resolved_base_url = (base_url or VLLM_DEFAULT_BASE_URL).strip().rstrip("/")
    if not resolved_base_url:
        resolved_base_url = VLLM_DEFAULT_BASE_URL
    models = discover_vllm_models(
        resolved_base_url,
        api_key=api_key,
        quiet=quiet,
    )
    return {
        "baseUrl": resolved_base_url,
        "api": "openai-completions",
        "models": models,
    }


__all__ = [
    "ProviderModelConfig",
    "ProviderConfig",
    "ExistingProviderConfig",
    "ProviderConfigMap",
    "normalize_provider_key",
    "normalize_api_key_config",
    "is_non_secret_api_key_marker",
    "provider_env_api_key_candidates",
    "resolve_env_api_key_var_name",
    "resolve_aws_sdk_api_key_var_name",
    "resolve_ollama_api_base",
    "discover_ollama_models",
    "discover_vllm_models",
    "normalize_providers",
    "build_ollama_provider",
    "build_vllm_provider",
    "MINIMAX_OAUTH_MARKER",
    "QWEN_OAUTH_MARKER",
    "OLLAMA_LOCAL_AUTH_MARKER",
    "NON_ENV_SECRETREF_MARKER",
]

"""Model auth — ported from bk/src/agents/model-auth.ts.

API key resolution for model providers from config and environment.
"""
from __future__ import annotations
import os
import logging
from typing import Any

log = logging.getLogger("openclaw.agents.model_auth")

# Common environment variable mappings per provider
PROVIDER_ENV_VARS: dict[str, list[str]] = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "cohere": ["COHERE_API_KEY", "CO_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY", "PPLX_API_KEY"],
    "ollama": [],
    "bedrock": ["AWS_ACCESS_KEY_ID"],
    "vertex": ["GOOGLE_APPLICATION_CREDENTIALS"],
}

def resolve_api_key_from_env(provider: str) -> str | None:
    env_vars = PROVIDER_ENV_VARS.get(provider.lower(), [])
    for var in env_vars:
        value = os.environ.get(var, "").strip()
        if value:
            return value
    generic = os.environ.get(f"{provider.upper()}_API_KEY", "").strip()
    return generic or None

def resolve_api_key(
    provider: str,
    config: dict[str, Any] | None = None,
    explicit_key: str | None = None,
) -> str | None:
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    if config:
        key = config.get("providers", {}).get(provider, {}).get("apiKey", "")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return resolve_api_key_from_env(provider)

def has_api_key(provider: str, config: dict[str, Any] | None = None) -> bool:
    return resolve_api_key(provider, config) is not None

def list_configured_providers(config: dict[str, Any] | None = None) -> list[str]:
    providers: list[str] = []
    for provider in PROVIDER_ENV_VARS:
        if has_api_key(provider, config):
            providers.append(provider)
    return providers

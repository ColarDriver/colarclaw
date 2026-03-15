"""LLM provider implementations.

Ported from bk/src/agents/pi-embedded-runner and models-config.providers.ts

Supports:
  openai / azure / openrouter / groq / ... (any OpenAI-compatible endpoint)
  anthropic / amazon-bedrock (Claude)
  google / gemini
  ollama (native API)
  echo (stub – always available, good for tests)

The provider is selected based on the model key prefix: ``provider/model-name``.
Override endpoints via env vars (see each class docstring).
"""
from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any, AsyncIterator, Protocol, runtime_checkable

logger = logging.getLogger("openclaw.llm.providers")


_PROVIDER_ALIASES: dict[str, str] = {
    "claude": "anthropic",
    "gemini": "google",
}

_OPENAI_COMPAT_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "together": "https://api.together.xyz/v1",
    "anyscale": "https://api.endpoints.anyscale.com/v1",
    "perplexity": "https://api.perplexity.ai",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "huggingface": "https://router.huggingface.co/v1",
}

_OPENAI_COMPAT_API_KEY_ENV: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "azure": ["AZURE_OPENAI_API_KEY", "AZURE_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "anyscale": ["ANYSCALE_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY", "PPLX_API_KEY"],
    "nvidia": ["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"],
    "vercel-ai-gateway": ["AI_GATEWAY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY"],
    "cloudflare-ai-gateway": ["CLOUDFLARE_AI_GATEWAY_API_KEY"],
    "volcengine": ["VOLC_API_KEY", "ARK_API_KEY", "VOLCENGINE_API_KEY"],
    "byteplus": ["BYTEPLUS_API_KEY"],
    "opencode": ["OPENCODE_API_KEY"],
    "zai": ["ZAI_API_KEY", "BIGMODEL_API_KEY"],
    "qwen-portal": ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
    "huggingface": ["HF_TOKEN", "HUGGINGFACE_API_KEY"],
}

_OPENAI_COMPAT_BASE_URL_ENV: dict[str, list[str]] = {
    "openai": ["OPENAI_BASE_URL"],
    "azure": ["AZURE_OPENAI_ENDPOINT", "AZURE_BASE_URL"],
    "openrouter": ["OPENROUTER_BASE_URL"],
    "groq": ["GROQ_BASE_URL"],
    "fireworks": ["FIREWORKS_BASE_URL"],
    "together": ["TOGETHER_BASE_URL"],
    "anyscale": ["ANYSCALE_BASE_URL"],
    "perplexity": ["PERPLEXITY_BASE_URL"],
    "nvidia": ["NVIDIA_BASE_URL"],
    "vercel-ai-gateway": ["AI_GATEWAY_BASE_URL", "VERCEL_AI_GATEWAY_BASE_URL"],
    "cloudflare-ai-gateway": ["CLOUDFLARE_AI_GATEWAY_BASE_URL"],
    "volcengine": ["VOLC_BASE_URL", "ARK_BASE_URL", "VOLCENGINE_BASE_URL"],
    "byteplus": ["BYTEPLUS_BASE_URL"],
    "opencode": ["OPENCODE_BASE_URL"],
    "zai": ["ZAI_BASE_URL", "BIGMODEL_BASE_URL"],
    "qwen-portal": ["QWEN_BASE_URL", "DASHSCOPE_BASE_URL"],
    "huggingface": ["HUGGINGFACE_BASE_URL", "HF_BASE_URL"],
}

_ANTHROPIC_API_KEY_ENV: dict[str, list[str]] = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "amazon-bedrock": ["AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID"],
    "kimi-coding": ["KIMI_API_KEY", "KIMI_CODING_API_KEY", "MOONSHOT_API_KEY"],
}

_ANTHROPIC_BASE_URL_ENV: dict[str, list[str]] = {
    "anthropic": ["ANTHROPIC_BASE_URL"],
    "amazon-bedrock": ["AMAZON_BEDROCK_BASE_URL", "BEDROCK_BASE_URL"],
    "kimi-coding": ["KIMI_BASE_URL", "KIMI_CODING_BASE_URL", "MOONSHOT_BASE_URL"],
}

_ANTHROPIC_DEFAULT_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "kimi-coding": "https://api.kimi.com/coding/v1",
}

_GEMINI_API_KEY_ENV: dict[str, list[str]] = {
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
}

_GEMINI_BASE_URL_ENV: dict[str, list[str]] = {
    "google": ["GEMINI_BASE_URL", "GOOGLE_BASE_URL"],
}

_CUSTOM_PROVIDER_API_TO_CLASS: dict[str, str] = {
    "openai-completions": "openai",
    "anthropic-messages": "anthropic",
}


def canonical_provider_id(provider: str) -> str:
    normalized = provider.strip().lower()
    if not normalized:
        return normalized
    return _PROVIDER_ALIASES.get(normalized, normalized)


def _as_provider_entry(
    provider_configs: Mapping[str, Any] | None,
    provider_id: str,
) -> dict[str, Any] | None:
    if not isinstance(provider_configs, Mapping):
        return None
    direct = provider_configs.get(provider_id)
    if isinstance(direct, Mapping):
        return dict(direct)
    canonical = canonical_provider_id(provider_id)
    via_canonical = provider_configs.get(canonical)
    if isinstance(via_canonical, Mapping):
        return dict(via_canonical)
    return None


def _provider_entry_api(provider_entry: Mapping[str, Any] | None) -> str:
    if not isinstance(provider_entry, Mapping):
        return ""
    raw = provider_entry.get("api")
    if isinstance(raw, str):
        return raw.strip().lower()
    return ""


def _provider_entry_text(provider_entry: Mapping[str, Any] | None, field: str) -> str:
    if not isinstance(provider_entry, Mapping):
        return ""
    raw = provider_entry.get(field)
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _resolve_from_env(candidates: list[str]) -> str:
    for env_name in candidates:
        raw = os.getenv(env_name, "")
        if raw.strip():
            return raw.strip()
    return ""


def _resolve_openai_compat_api_key(provider_id: str) -> str:
    canonical = canonical_provider_id(provider_id)
    env_candidates = list(_OPENAI_COMPAT_API_KEY_ENV.get(canonical, ()))
    fallback_name = f"{canonical.upper().replace('-', '_')}_API_KEY"
    if fallback_name not in env_candidates:
        env_candidates.append(fallback_name)
    return _resolve_from_env(env_candidates)


def _resolve_openai_compat_base_url(provider_id: str) -> str:
    canonical = canonical_provider_id(provider_id)
    env_candidates = list(_OPENAI_COMPAT_BASE_URL_ENV.get(canonical, ()))
    fallback_name = f"{canonical.upper().replace('-', '_')}_BASE_URL"
    if fallback_name not in env_candidates:
        env_candidates.append(fallback_name)
    env_url = _resolve_from_env(env_candidates)
    if env_url:
        return _normalize_openai_compat_base_url(canonical, env_url)
    default_url = _OPENAI_COMPAT_DEFAULT_BASE_URLS.get(
        canonical,
        OpenAICompatibleProvider.DEFAULT_BASE_URL,
    )
    return _normalize_openai_compat_base_url(canonical, default_url)


def _normalize_openai_compat_base_url(provider_id: str, base_url: str) -> str:
    canonical = canonical_provider_id(provider_id)
    normalized = base_url.strip().rstrip("/")
    if canonical == "kimi-coding" and normalized.endswith("/coding"):
        return f"{normalized}/v1"
    return normalized


def _resolve_anthropic_api_key(provider_id: str) -> str:
    canonical = canonical_provider_id(provider_id)
    env_candidates = list(_ANTHROPIC_API_KEY_ENV.get(canonical, ()))
    fallback_name = f"{canonical.upper().replace('-', '_')}_API_KEY"
    if fallback_name not in env_candidates:
        env_candidates.append(fallback_name)
    return _resolve_from_env(env_candidates)


def _resolve_anthropic_base_url(provider_id: str) -> str:
    canonical = canonical_provider_id(provider_id)
    env_candidates = list(_ANTHROPIC_BASE_URL_ENV.get(canonical, ()))
    fallback_name = f"{canonical.upper().replace('-', '_')}_BASE_URL"
    if fallback_name not in env_candidates:
        env_candidates.append(fallback_name)
    env_url = _resolve_from_env(env_candidates)
    default_url = _ANTHROPIC_DEFAULT_BASE_URLS.get(canonical, AnthropicProvider.BASE_URL)
    return _normalize_anthropic_base_url(canonical, env_url or default_url)


def _normalize_anthropic_base_url(provider_id: str, base_url: str) -> str:
    canonical = canonical_provider_id(provider_id)
    normalized = base_url.strip().rstrip("/")
    if canonical == "kimi-coding" and normalized.endswith("/coding"):
        return f"{normalized}/v1"
    return normalized


def _resolve_gemini_api_key(provider_id: str) -> str:
    canonical = canonical_provider_id(provider_id)
    env_candidates = list(_GEMINI_API_KEY_ENV.get(canonical, ()))
    fallback_name = f"{canonical.upper().replace('-', '_')}_API_KEY"
    if fallback_name not in env_candidates:
        env_candidates.append(fallback_name)
    return _resolve_from_env(env_candidates)


def _resolve_gemini_base_url(provider_id: str) -> str:
    canonical = canonical_provider_id(provider_id)
    env_candidates = list(_GEMINI_BASE_URL_ENV.get(canonical, ()))
    fallback_name = f"{canonical.upper().replace('-', '_')}_BASE_URL"
    if fallback_name not in env_candidates:
        env_candidates.append(fallback_name)
    env_url = _resolve_from_env(env_candidates)
    return env_url or GeminiProvider.BASE_URL


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMProvider(Protocol):
    async def generate(self, *, model: str, messages: list[dict], **kwargs) -> str: ...
    async def stream(self, *, model: str, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...


# ---------------------------------------------------------------------------
# Echo (stub – no network calls)
# ---------------------------------------------------------------------------

class EchoProvider:
    """Returns the last user message prefixed with [ECHO:model]. Used for tests."""

    async def generate(self, *, model: str, messages: list[dict], **kwargs) -> str:
        last = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "(empty)",
        )
        return f"[ECHO:{model}] {str(last)[:2000]}"

    async def stream(self, *, model: str, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        text = await self.generate(model=model, messages=messages, **kwargs)

        async def _gen():
            yield text

        return _gen()


# ---------------------------------------------------------------------------
# OpenAI-compatible provider
# ---------------------------------------------------------------------------

class OpenAICompatibleProvider:
    """Calls any OpenAI-compatible /v1/chat/completions endpoint.

    Env vars:
      OPENAI_API_KEY   – API key (use "ollama" / "lm-studio" for local servers)
      OPENAI_BASE_URL  – Override base URL (e.g. http://localhost:11434/v1)
    """

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_base_url: str | None = None,
    ) -> None:
        resolved_default = (default_base_url or self.DEFAULT_BASE_URL).strip() or self.DEFAULT_BASE_URL
        self._api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self._base_url = (base_url or os.getenv("OPENAI_BASE_URL", resolved_default)).rstrip("/")

    def _strip_provider(self, model: str) -> str:
        return model.split("/", 1)[-1] if "/" in model else model

    @staticmethod
    def _request_error_message(resp) -> str:
        body = ""
        try:
            body = resp.text.strip()
        except Exception:
            body = ""
        if body:
            return (
                f"provider HTTP {resp.status_code} at {resp.request.url}: {body[:400]}"
            )
        return f"provider HTTP {resp.status_code} at {resp.request.url}"

    async def generate(self, *, model: str, messages: list[dict], **kwargs) -> str:
        import httpx

        model_id = self._strip_provider(model)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        body: dict = {
            "model": model_id,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            if resp.status_code >= 400:
                raise RuntimeError(self._request_error_message(resp))
            data = resp.json()
            return str(data["choices"][0]["message"]["content"])

    async def stream(self, *, model: str, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        import httpx

        model_id = self._strip_provider(model)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        body: dict = {
            "model": model_id,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": True,
        }

        async def _gen() -> AsyncIterator[str]:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=body,
                ) as resp:
                    if resp.status_code >= 400:
                        detail = ""
                        try:
                            raw = await resp.aread()
                            detail = raw.decode("utf-8", errors="ignore").strip()
                        except Exception:
                            detail = ""
                        if detail:
                            raise RuntimeError(
                                f"provider HTTP {resp.status_code} at {resp.request.url}: {detail[:400]}"
                            )
                        raise RuntimeError(
                            f"provider HTTP {resp.status_code} at {resp.request.url}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload.strip() == "[DONE]":
                            break
                        try:
                            import json
                            chunk = json.loads(payload)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            pass

        return _gen()


# ---------------------------------------------------------------------------
# Anthropic Claude
# ---------------------------------------------------------------------------

class AnthropicProvider:
    """Calls Anthropic's messages API.

    Env vars:
      ANTHROPIC_API_KEY – required
    """

    BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = (api_key or os.getenv("ANTHROPIC_API_KEY", "")).strip()
        self._base_url = (base_url or os.getenv("ANTHROPIC_BASE_URL", self.BASE_URL)).rstrip("/")

    def _strip_provider(self, model: str) -> str:
        return model.split("/", 1)[-1] if "/" in model else model

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
        }

    async def generate(self, *, model: str, messages: list[dict], **kwargs) -> str:
        import httpx

        model_id = self._strip_provider(model)
        # Anthropic needs system prompt separated
        system = ""
        api_messages = []
        for m in messages:
            if m.get("role") == "system":
                system += m.get("content", "")
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        body: dict = {
            "model": model_id,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": api_messages,
        }
        if system:
            body["system"] = system

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/messages",
                headers=self._headers(),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data["content"][0]["text"])

    async def stream(self, *, model: str, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        import httpx
        import json

        model_id = self._strip_provider(model)
        system = ""
        api_messages = []
        for m in messages:
            if m.get("role") == "system":
                system += m.get("content", "")
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        body: dict = {
            "model": model_id,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": api_messages,
            "stream": True,
        }
        if system:
            body["system"] = system

        async def _gen() -> AsyncIterator[str]:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/messages",
                    headers=self._headers(),
                    json=body,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        try:
                            event = json.loads(payload)
                            if event.get("type") == "content_block_delta":
                                delta = event.get("delta", {}).get("text", "")
                                if delta:
                                    yield delta
                        except Exception:
                            pass

        return _gen()


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiProvider:
    """Calls Google's Gemini generateContent or streamGenerateContent API.

    Env vars:
      GEMINI_API_KEY – required
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self._base_url = (base_url or os.getenv("GEMINI_BASE_URL", self.BASE_URL)).rstrip("/")

    def _strip_provider(self, model: str) -> str:
        return model.split("/", 1)[-1] if "/" in model else model

    def _messages_to_gemini(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Convert OpenAI-format messages to Gemini format."""
        system = ""
        contents = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system += content
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})
            else:
                contents.append({"role": "user", "parts": [{"text": content}]})
        return system, contents

    async def generate(self, *, model: str, messages: list[dict], **kwargs) -> str:
        import httpx

        model_id = self._strip_provider(model)
        system, contents = self._messages_to_gemini(messages)
        url = f"{self._base_url}/models/{model_id}:generateContent?key={self._api_key}"
        body: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": kwargs.get("max_tokens", 4096),
                "temperature": kwargs.get("temperature", 0.7),
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            return str(data["candidates"][0]["content"]["parts"][0]["text"])

    async def stream(self, *, model: str, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        import httpx
        import json

        model_id = self._strip_provider(model)
        system, contents = self._messages_to_gemini(messages)
        url = f"{self._base_url}/models/{model_id}:streamGenerateContent?key={self._api_key}&alt=sse"
        body: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": kwargs.get("max_tokens", 4096),
                "temperature": kwargs.get("temperature", 0.7),
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        async def _gen() -> AsyncIterator[str]:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=body) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        try:
                            chunk = json.loads(payload)
                            text = chunk["candidates"][0]["content"]["parts"][0].get("text", "")
                            if text:
                                yield text
                        except Exception:
                            pass

        return _gen()


# ---------------------------------------------------------------------------
# Ollama (native API)
# ---------------------------------------------------------------------------

class OllamaProvider:
    """Calls Ollama's /api/chat endpoint directly.

    Env vars:
      OLLAMA_BASE_URL – default http://localhost:11434
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (
            base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")

    def _strip_provider(self, model: str) -> str:
        return model.split("/", 1)[-1] if "/" in model else model

    async def generate(self, *, model: str, messages: list[dict], **kwargs) -> str:
        import httpx

        model_id = self._strip_provider(model)
        body = {
            "model": model_id,
            "messages": messages,
            "stream": False,
            "options": {"temperature": kwargs.get("temperature", 0.7)},
        }
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
            return str(data["message"]["content"])

    async def stream(self, *, model: str, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        import httpx
        import json

        model_id = self._strip_provider(model)
        body = {
            "model": model_id,
            "messages": messages,
            "stream": True,
            "options": {"temperature": kwargs.get("temperature", 0.7)},
        }

        async def _gen() -> AsyncIterator[str]:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", f"{self._base_url}/api/chat", json=body) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            content = chunk.get("message", {}).get("content", "")
                            if content:
                                yield content
                            if chunk.get("done"):
                                break
                        except Exception:
                            pass

        return _gen()


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

_PROVIDER_REGISTRY: dict[str, type] = {
    "openai": OpenAICompatibleProvider,
    "azure": OpenAICompatibleProvider,
    "openrouter": OpenAICompatibleProvider,
    "groq": OpenAICompatibleProvider,
    "fireworks": OpenAICompatibleProvider,
    "together": OpenAICompatibleProvider,
    "anyscale": OpenAICompatibleProvider,
    "perplexity": OpenAICompatibleProvider,
    "nvidia": OpenAICompatibleProvider,
    "vercel-ai-gateway": OpenAICompatibleProvider,
    "cloudflare-ai-gateway": OpenAICompatibleProvider,
    "volcengine": OpenAICompatibleProvider,
    "byteplus": OpenAICompatibleProvider,
    "opencode": OpenAICompatibleProvider,
    "zai": OpenAICompatibleProvider,
    "qwen-portal": OpenAICompatibleProvider,
    "huggingface": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "amazon-bedrock": AnthropicProvider,
    "kimi-coding": AnthropicProvider,
    "claude": AnthropicProvider,
    "google": GeminiProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "echo": EchoProvider,
}


_OPENAI_COMPAT_PROVIDER_IDS: set[str] = {
    canonical_provider_id(provider_id)
    for provider_id, provider_cls in _PROVIDER_REGISTRY.items()
    if provider_cls is OpenAICompatibleProvider
}
_ANTHROPIC_PROVIDER_IDS: set[str] = {
    canonical_provider_id(provider_id)
    for provider_id, provider_cls in _PROVIDER_REGISTRY.items()
    if provider_cls is AnthropicProvider
}
_GEMINI_PROVIDER_IDS: set[str] = {
    canonical_provider_id(provider_id)
    for provider_id, provider_cls in _PROVIDER_REGISTRY.items()
    if provider_cls is GeminiProvider
}
_OLLAMA_PROVIDER_IDS: set[str] = {
    canonical_provider_id(provider_id)
    for provider_id, provider_cls in _PROVIDER_REGISTRY.items()
    if provider_cls is OllamaProvider
}


def list_registered_provider_ids(
    *,
    include_aliases: bool = True,
    include_echo: bool = False,
) -> list[str]:
    ids = sorted(_PROVIDER_REGISTRY.keys())
    if not include_aliases:
        ids = [provider_id for provider_id in ids if canonical_provider_id(provider_id) == provider_id]
    if not include_echo:
        ids = [provider_id for provider_id in ids if provider_id != "echo"]
    return ids


def list_provider_aliases() -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for alias, canonical in _PROVIDER_ALIASES.items():
        aliases.setdefault(canonical, []).append(alias)
    for values in aliases.values():
        values.sort()
    return aliases


def list_custom_provider_protocols() -> list[str]:
    return sorted(_CUSTOM_PROVIDER_API_TO_CLASS.keys())


def provider_api_protocol(
    provider_id: str,
    provider_entry: Mapping[str, Any] | None = None,
) -> str:
    api = _provider_entry_api(provider_entry)
    if api in _CUSTOM_PROVIDER_API_TO_CLASS:
        return api
    canonical = canonical_provider_id(provider_id)
    if canonical in _OPENAI_COMPAT_PROVIDER_IDS:
        return "openai-completions"
    if canonical in _ANTHROPIC_PROVIDER_IDS:
        return "anthropic-messages"
    if canonical in _GEMINI_PROVIDER_IDS:
        return "google-generativelanguage"
    if canonical in _OLLAMA_PROVIDER_IDS:
        return "ollama-native"
    if canonical == "echo":
        return "echo"
    return "openai-completions"


def resolve_provider(
    model_key: str,
    provider_configs: Mapping[str, Any] | None = None,
) -> LLMProvider:
    """Return a provider instance for the given ``provider/model`` key.

    Selection order:
    1. Explicit prefix from the model key (e.g. ``anthropic/…``).
    2. Provider config map (api/baseUrl/apiKey) from runtime config.
    3. Environment-variable fallback by provider family.
    3. EchoProvider as final fallback (no network calls, good for dev/test).
    """
    prefix = model_key.split("/", 1)[0].strip().lower() if "/" in model_key else ""
    canonical = canonical_provider_id(prefix)
    provider_entry = _as_provider_entry(provider_configs, prefix or canonical)
    provider_api = _provider_entry_api(provider_entry)
    provider_api_class = _CUSTOM_PROVIDER_API_TO_CLASS.get(provider_api, "")

    # Custom providers route by explicit API protocol.
    if provider_api_class == "openai":
        api_key = _provider_entry_text(provider_entry, "apiKey") or _resolve_openai_compat_api_key(prefix or canonical)
        base_url = _normalize_openai_compat_base_url(
            prefix or canonical,
            _provider_entry_text(provider_entry, "baseUrl")
            or _resolve_openai_compat_base_url(prefix or canonical),
        )
        default_base_url = _OPENAI_COMPAT_DEFAULT_BASE_URLS.get(
            canonical_provider_id(prefix or canonical),
            OpenAICompatibleProvider.DEFAULT_BASE_URL,
        )
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url,
            default_base_url=default_base_url,
        )

    if provider_api_class == "anthropic":
        api_key = _provider_entry_text(provider_entry, "apiKey") or _resolve_anthropic_api_key(prefix or canonical)
        base_url = _normalize_anthropic_base_url(
            prefix or canonical,
            _provider_entry_text(provider_entry, "baseUrl")
            or _resolve_anthropic_base_url(prefix or canonical),
        )
        return AnthropicProvider(api_key=api_key, base_url=base_url)

    provider_id = canonical
    if provider_id in _OPENAI_COMPAT_PROVIDER_IDS:
        api_key = _provider_entry_text(provider_entry, "apiKey") or _resolve_openai_compat_api_key(provider_id)
        base_url = _normalize_openai_compat_base_url(
            provider_id,
            _provider_entry_text(provider_entry, "baseUrl")
            or _resolve_openai_compat_base_url(provider_id),
        )
        default_base_url = _OPENAI_COMPAT_DEFAULT_BASE_URLS.get(
            provider_id,
            OpenAICompatibleProvider.DEFAULT_BASE_URL,
        )
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url,
            default_base_url=default_base_url,
        )

    if provider_id in _ANTHROPIC_PROVIDER_IDS:
        api_key = _provider_entry_text(provider_entry, "apiKey") or _resolve_anthropic_api_key(provider_id)
        base_url = _normalize_anthropic_base_url(
            provider_id,
            _provider_entry_text(provider_entry, "baseUrl")
            or _resolve_anthropic_base_url(provider_id),
        )
        return AnthropicProvider(api_key=api_key, base_url=base_url)

    if provider_id in _GEMINI_PROVIDER_IDS:
        api_key = _provider_entry_text(provider_entry, "apiKey") or _resolve_gemini_api_key(provider_id)
        base_url = _provider_entry_text(provider_entry, "baseUrl") or _resolve_gemini_base_url(provider_id)
        return GeminiProvider(api_key=api_key, base_url=base_url)

    if provider_id in _OLLAMA_PROVIDER_IDS:
        base_url = _provider_entry_text(provider_entry, "baseUrl") or None
        return OllamaProvider(base_url=base_url)

    if provider_id == "echo":
        return EchoProvider()

    # Heuristic fallback based on env keys
    if os.getenv("OPENAI_API_KEY"):
        logger.info("Unknown provider prefix '%s'; falling back to OpenAI-compatible", prefix)
        return OpenAICompatibleProvider()
    if os.getenv("ANTHROPIC_API_KEY"):
        logger.info("Unknown provider prefix '%s'; falling back to Anthropic", prefix)
        return AnthropicProvider()
    if os.getenv("GEMINI_API_KEY"):
        logger.info("Unknown provider prefix '%s'; falling back to Gemini", prefix)
        return GeminiProvider()
    if os.getenv("OLLAMA_BASE_URL") or _ollama_alive():
        logger.info("Unknown provider prefix '%s'; falling back to Ollama", prefix)
        return OllamaProvider()

    logger.warning("No LLM API key found; using EchoProvider for model '%s'", model_key)
    return EchoProvider()


def _ollama_alive() -> bool:
    """Quick sync check if Ollama is running locally (best-effort)."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.5):
            return True
    except OSError:
        return False

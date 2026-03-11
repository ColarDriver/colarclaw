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
from typing import AsyncIterator, Protocol, runtime_checkable

logger = logging.getLogger("openclaw.llm.providers")


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
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._base_url = (base_url or os.getenv("OPENAI_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")

    def _strip_provider(self, model: str) -> str:
        return model.split("/", 1)[-1] if "/" in model else model

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
            resp.raise_for_status()
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
                    resp.raise_for_status()
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

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")

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
                f"{self.BASE_URL}/messages",
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
                    f"{self.BASE_URL}/messages",
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

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")

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
        url = f"{self.BASE_URL}/models/{model_id}:generateContent?key={self._api_key}"
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
        url = f"{self.BASE_URL}/models/{model_id}:streamGenerateContent?key={self._api_key}&alt=sse"
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
    "kimi-coding": OpenAICompatibleProvider,
    "opencode": OpenAICompatibleProvider,
    "zai": OpenAICompatibleProvider,
    "qwen-portal": OpenAICompatibleProvider,
    "huggingface": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "amazon-bedrock": AnthropicProvider,
    "claude": AnthropicProvider,
    "google": GeminiProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "echo": EchoProvider,
}


def resolve_provider(model_key: str) -> LLMProvider:
    """Return a provider instance for the given ``provider/model`` key.

    Selection order:
    1. Explicit prefix from the model key (e.g. ``anthropic/…``).
    2. Heuristic: whichever env-key is set (OPENAI_API_KEY, ANTHROPIC_API_KEY, …).
    3. EchoProvider as final fallback (no network calls, good for dev/test).
    """
    prefix = model_key.split("/", 1)[0].lower() if "/" in model_key else ""
    provider_cls = _PROVIDER_REGISTRY.get(prefix)

    if provider_cls is not None:
        return provider_cls()

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

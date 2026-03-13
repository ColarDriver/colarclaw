"""LLM routing layer.

Wraps llm.providers to provide:
- Multi-model fallback (primary → fallback1 → fallback2 …)
- Message-list based API (not raw prompt strings)
- System prompt injection
- Registry-aware model validation (skip unknown models)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models.registry import ModelRegistry
from .providers import resolve_provider, EchoProvider

logger = logging.getLogger("openclaw.llm.router")


@dataclass(frozen=True)
class RouterResult:
    text: str
    model: str
    provider: str
    fallback_used: bool


class LlmRouter:
    """Routes LLM calls to the appropriate provider with fallback support."""

    def __init__(
        self,
        *,
        default_model: str,
        fallback_models: tuple[str, ...],
        model_registry: ModelRegistry,
    ) -> None:
        self._default_model = default_model
        self._fallback_models = fallback_models
        self._model_registry = model_registry

    async def run(
        self,
        *,
        prompt: str,
        preferred_model: str | None = None,
        system_prompt: str | None = None,
        messages: list[dict] | None = None,
    ) -> RouterResult:
        """
        Generate a response.

        Args:
            prompt: User message text (used if messages is None).
            preferred_model: Override model for this call only.
            system_prompt: Optional system prompt prepended to messages.
            messages: Pre-built message list.  If provided, prompt is ignored.

        Returns:
            RouterResult with generated text and metadata.
        """
        model_candidates = [
            m for m in [preferred_model or self._default_model, *self._fallback_models]
            if m
        ]

        # Build message list once
        if messages is None:
            msg_list: list[dict] = []
            if system_prompt:
                msg_list.append({"role": "system", "content": system_prompt})
            msg_list.append({"role": "user", "content": prompt})
        else:
            msg_list = list(messages)
            if system_prompt and (not msg_list or msg_list[0].get("role") != "system"):
                msg_list = [{"role": "system", "content": system_prompt}] + msg_list

        last_error: Exception | None = None
        for index, model in enumerate(model_candidates):
            # Skip models not in the registry (unless registry is empty = allow all)
            if self._model_registry.keys() and not self._model_registry.has(model):
                logger.warning("model not in registry, skipping: %s", model)
                continue

            provider = resolve_provider(model)
            provider_name = type(provider).__name__

            try:
                text = await provider.generate(model=model, messages=msg_list)
                if index > 0:
                    logger.info("fell back to model=%s provider=%s", model, provider_name)
                return RouterResult(
                    text=text,
                    model=model,
                    provider=provider_name,
                    fallback_used=index > 0,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "provider call failed model=%s provider=%s error=%s",
                    model,
                    provider_name,
                    str(exc)[:300],
                )

        if last_error is not None:
            raise RuntimeError(f"all model fallbacks exhausted: {last_error}") from last_error
        raise RuntimeError("no available model (registry empty or all skipped)")

    async def stream(
        self,
        *,
        prompt: str,
        preferred_model: str | None = None,
        system_prompt: str | None = None,
        messages: list[dict] | None = None,
    ):
        """Stream tokens from the first available model.

        Yields str tokens.  Falls back like run() but only for the first chunk
        (once streaming starts there's no fallback mid-stream).
        """
        model_candidates = [
            m for m in [preferred_model or self._default_model, *self._fallback_models]
            if m
        ]

        if messages is None:
            msg_list: list[dict] = []
            if system_prompt:
                msg_list.append({"role": "system", "content": system_prompt})
            msg_list.append({"role": "user", "content": prompt})
        else:
            msg_list = list(messages)
            if system_prompt and (not msg_list or msg_list[0].get("role") != "system"):
                msg_list = [{"role": "system", "content": system_prompt}] + msg_list

        last_error: Exception | None = None
        for model in model_candidates:
            if self._model_registry.keys() and not self._model_registry.has(model):
                continue
            provider = resolve_provider(model)
            try:
                gen = await provider.stream(model=model, messages=msg_list)
                async for token in gen:
                    yield token
                return
            except Exception as exc:
                last_error = exc
                logger.warning("stream failed model=%s error=%s", model, str(exc)[:200])

        raise RuntimeError(f"all stream fallbacks exhausted: {last_error}") from last_error

    def update_models(
        self,
        *,
        default_model: str,
        fallback_models: tuple[str, ...],
    ) -> None:
        self._default_model = default_model
        self._fallback_models = fallback_models

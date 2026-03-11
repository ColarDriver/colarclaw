"""Model compatibility layer — ported from bk/src/agents/model-compat.ts.

Handles provider-specific quirks:
- OpenAI non-native endpoints: disable 'developer' role and streaming usage
- Anthropic: strip trailing /v1 from base URLs
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass
class ModelCompat:
    supports_developer_role: bool = True
    supports_usage_in_streaming: bool = True


@dataclass
class ModelSpec:
    api: str
    model: str
    base_url: str = ""
    compat: ModelCompat | None = None
    # pass-through for other fields
    extra: dict[str, Any] | None = None


def _is_openai_native_endpoint(base_url: str) -> bool:
    """Returns True only for confirmed native OpenAI infrastructure."""
    try:
        host = urlparse(base_url).hostname
        if host is None:
            return False
        return host.lower() == "api.openai.com"
    except Exception:
        return False


def _normalize_anthropic_base_url(base_url: str) -> str:
    """Strip trailing /v1 that users may include — the SDK appends /v1/messages itself."""
    import re
    return re.sub(r"/v1/?$", "", base_url)


def normalize_model_compat(spec: ModelSpec) -> ModelSpec:
    """Apply provider-specific compatibility normalizations to a model spec."""
    base_url = spec.base_url or ""

    # Anthropic: strip trailing /v1
    if spec.api == "anthropic-messages" and base_url:
        normalised = _normalize_anthropic_base_url(base_url)
        if normalised != base_url:
            return ModelSpec(
                api=spec.api,
                model=spec.model,
                base_url=normalised,
                compat=spec.compat,
                extra=spec.extra,
            )

    if spec.api != "openai-completions":
        return spec

    # OpenAI-compatible: force both compat flags off for non-native endpoints
    compat = spec.compat
    needs_force = bool(base_url) and not _is_openai_native_endpoint(base_url)
    if not needs_force:
        return spec

    if (
        compat is not None
        and not compat.supports_developer_role
        and not compat.supports_usage_in_streaming
    ):
        return spec

    new_compat = ModelCompat(
        supports_developer_role=False,
        supports_usage_in_streaming=False,
    )
    return ModelSpec(
        api=spec.api,
        model=spec.model,
        base_url=spec.base_url,
        compat=new_compat,
        extra=spec.extra,
    )

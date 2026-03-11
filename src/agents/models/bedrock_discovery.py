"""Bedrock discovery — ported from bk/src/agents/bedrock-discovery.ts.

AWS Bedrock model discovery with caching. Lists foundation models from
AWS Bedrock and converts them into model definition configs.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("openclaw.agents.bedrock_discovery")

DEFAULT_REFRESH_INTERVAL_SECONDS = 3600
DEFAULT_CONTEXT_WINDOW = 32000
DEFAULT_MAX_TOKENS = 4096
DEFAULT_COST = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

_discovery_cache: dict[str, dict[str, Any]] = {}
_has_logged_bedrock_error = False


def _normalize_provider_filter(filter_list: list[str] | None) -> list[str]:
    if not filter_list:
        return []
    normalized = sorted(set(
        entry.strip().lower() for entry in filter_list if entry.strip()
    ))
    return normalized


def _build_cache_key(
    region: str,
    provider_filter: list[str],
    refresh_interval_seconds: int,
    default_context_window: int,
    default_max_tokens: int,
) -> str:
    return json.dumps({
        "region": region,
        "providerFilter": provider_filter,
        "refreshIntervalSeconds": refresh_interval_seconds,
        "defaultContextWindow": default_context_window,
        "defaultMaxTokens": default_max_tokens,
    })


def _includes_text_modalities(modalities: list[str] | None) -> bool:
    return any(m.lower() == "text" for m in (modalities or []))


def _is_active(summary: dict[str, Any]) -> bool:
    status = (summary.get("modelLifecycle") or {}).get("status", "")
    return isinstance(status, str) and status.upper() == "ACTIVE"


def _map_input_modalities(summary: dict[str, Any]) -> list[str]:
    inputs = summary.get("inputModalities") or []
    mapped: set[str] = set()
    for modality in inputs:
        lower = modality.lower()
        if lower == "text":
            mapped.add("text")
        if lower == "image":
            mapped.add("image")
    if not mapped:
        mapped.add("text")
    return list(mapped)


def _infer_reasoning_support(summary: dict[str, Any]) -> bool:
    haystack = f"{summary.get('modelId', '')} {summary.get('modelName', '')}".lower()
    return "reasoning" in haystack or "thinking" in haystack


def _resolve_default_context_window(config: dict[str, Any] | None = None) -> int:
    if not config:
        return DEFAULT_CONTEXT_WINDOW
    value = int(config.get("defaultContextWindow", DEFAULT_CONTEXT_WINDOW) or DEFAULT_CONTEXT_WINDOW)
    return value if value > 0 else DEFAULT_CONTEXT_WINDOW


def _resolve_default_max_tokens(config: dict[str, Any] | None = None) -> int:
    if not config:
        return DEFAULT_MAX_TOKENS
    value = int(config.get("defaultMaxTokens", DEFAULT_MAX_TOKENS) or DEFAULT_MAX_TOKENS)
    return value if value > 0 else DEFAULT_MAX_TOKENS


def _matches_provider_filter(summary: dict[str, Any], filter_list: list[str]) -> bool:
    if not filter_list:
        return True
    provider_name = summary.get("providerName")
    if not provider_name:
        model_id = summary.get("modelId", "")
        provider_name = model_id.split(".")[0] if isinstance(model_id, str) else None
    normalized = (provider_name or "").strip().lower()
    if not normalized:
        return False
    return normalized in filter_list


def _should_include_summary(summary: dict[str, Any], filter_list: list[str]) -> bool:
    model_id = (summary.get("modelId") or "").strip()
    if not model_id:
        return False
    if not _matches_provider_filter(summary, filter_list):
        return False
    if summary.get("responseStreamingSupported") is not True:
        return False
    if not _includes_text_modalities(summary.get("outputModalities")):
        return False
    if not _is_active(summary):
        return False
    return True


def _to_model_definition(
    summary: dict[str, Any],
    context_window: int,
    max_tokens: int,
) -> dict[str, Any]:
    model_id = (summary.get("modelId") or "").strip()
    return {
        "id": model_id,
        "name": (summary.get("modelName") or "").strip() or model_id,
        "reasoning": _infer_reasoning_support(summary),
        "input": _map_input_modalities(summary),
        "cost": dict(DEFAULT_COST),
        "contextWindow": context_window,
        "maxTokens": max_tokens,
    }


def reset_bedrock_discovery_cache_for_test() -> None:
    global _has_logged_bedrock_error
    _discovery_cache.clear()
    _has_logged_bedrock_error = False


async def discover_bedrock_models(
    region: str,
    config: dict[str, Any] | None = None,
    now_fn: Any | None = None,
    client_factory: Any | None = None,
) -> list[dict[str, Any]]:
    """Discover Bedrock foundation models for a region."""
    global _has_logged_bedrock_error

    refresh_interval = max(0, int(
        (config or {}).get("refreshInterval", DEFAULT_REFRESH_INTERVAL_SECONDS)
        or DEFAULT_REFRESH_INTERVAL_SECONDS
    ))
    provider_filter = _normalize_provider_filter((config or {}).get("providerFilter"))
    default_context_window = _resolve_default_context_window(config)
    default_max_tokens = _resolve_default_max_tokens(config)

    cache_key = _build_cache_key(
        region, provider_filter, refresh_interval, default_context_window, default_max_tokens,
    )
    now = (now_fn() if now_fn else time.time() * 1000)

    if refresh_interval > 0:
        cached = _discovery_cache.get(cache_key)
        if cached and cached.get("value") and cached.get("expires_at", 0) > now:
            return cached["value"]

    try:
        import boto3
        factory = client_factory or (lambda r: boto3.client("bedrock", region_name=r))
        client = factory(region)
        response = client.list_foundation_models()
        summaries = response.get("modelSummaries", [])

        discovered = []
        for summary in summaries:
            if _should_include_summary(summary, provider_filter):
                discovered.append(_to_model_definition(summary, default_context_window, default_max_tokens))
        discovered.sort(key=lambda m: m.get("name", ""))

        if refresh_interval > 0:
            _discovery_cache[cache_key] = {
                "expires_at": now + refresh_interval * 1000,
                "value": discovered,
            }
        return discovered
    except Exception as error:
        if refresh_interval > 0:
            _discovery_cache.pop(cache_key, None)
        if not _has_logged_bedrock_error:
            _has_logged_bedrock_error = True
            log.warning("Failed to list models: %s", error)
        return []

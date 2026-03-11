"""Model scan — ported from bk/src/agents/model-scan.ts.

Scans available models from configured providers.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("openclaw.agents.model_scan")

@dataclass
class ScannedModel:
    id: str
    provider: str
    name: str | None = None
    context_length: int | None = None
    supports_vision: bool = False
    supports_tools: bool = False

@dataclass
class ModelScanResult:
    models: list[ScannedModel] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    providers_scanned: list[str] = field(default_factory=list)

async def scan_provider_models(
    provider: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[ScannedModel]:
    """Scan available models from a provider. Override for specific providers."""
    log.debug("Scanning models for provider=%s", provider)
    return []

async def scan_all_models(
    config: dict[str, Any] | None = None,
    providers: list[str] | None = None,
) -> ModelScanResult:
    result = ModelScanResult()
    target_providers = providers or []
    for provider in target_providers:
        try:
            models = await scan_provider_models(provider)
            result.models.extend(models)
            result.providers_scanned.append(provider)
        except Exception as e:
            result.errors.append(f"{provider}: {e}")
    return result

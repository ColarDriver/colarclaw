"""Pi embedded runner extra params — ported from bk/src/agents/pi-embedded-runner/extra-params.ts."""
from __future__ import annotations

from typing import Any


def build_extra_params(
    provider: str,
    model_id: str,
    config: Any = None,
) -> dict[str, Any]:
    """Build provider-specific extra parameters for API calls."""
    extra: dict[str, Any] = {}
    provider_lower = provider.lower()

    # OpenRouter-specific
    if provider_lower == "openrouter":
        extra["transforms"] = ["middle-out"]

    # Kilocode-specific
    if provider_lower == "kilocode":
        if config and hasattr(config, "kilocode"):
            kc = config.kilocode
            if hasattr(kc, "org_id") and kc.org_id:
                extra["organization"] = kc.org_id

    return extra


def merge_extra_params(
    base: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Merge extra params, overrides take precedence."""
    return {**base, **overrides}

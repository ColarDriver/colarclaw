"""Model overrides — ported from bk/src/sessions/model-overrides.ts.

Apply model/provider/profile overrides to session entries.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class ModelOverrideSelection:
    provider: str = ""
    model: str = ""
    is_default: bool = False


def apply_model_override_to_session_entry(
    entry: dict[str, Any],
    selection: ModelOverrideSelection,
    profile_override: str | None = None,
    profile_override_source: str = "user",
) -> bool:
    """Apply model override to a session entry. Returns True if updated."""
    updated = False
    selection_updated = False

    if selection.is_default:
        if entry.pop("providerOverride", None) is not None:
            updated = True
            selection_updated = True
        if entry.pop("modelOverride", None) is not None:
            updated = True
            selection_updated = True
    else:
        if entry.get("providerOverride") != selection.provider:
            entry["providerOverride"] = selection.provider
            updated = True
            selection_updated = True
        if entry.get("modelOverride") != selection.model:
            entry["modelOverride"] = selection.model
            updated = True
            selection_updated = True

    # Clear stale runtime model identity
    runtime_model = str(entry.get("model", "")).strip()
    runtime_provider = str(entry.get("modelProvider", "")).strip()
    runtime_present = bool(runtime_model) or bool(runtime_provider)
    runtime_aligned = (
        runtime_model == selection.model
        and (not runtime_provider or runtime_provider == selection.provider)
    )
    if runtime_present and (selection_updated or not runtime_aligned):
        if entry.pop("model", None) is not None:
            updated = True
        if entry.pop("modelProvider", None) is not None:
            updated = True

    if profile_override:
        if entry.get("authProfileOverride") != profile_override:
            entry["authProfileOverride"] = profile_override
            updated = True
        if entry.get("authProfileOverrideSource") != profile_override_source:
            entry["authProfileOverrideSource"] = profile_override_source
            updated = True
        if entry.pop("authProfileOverrideCompactionCount", None) is not None:
            updated = True
    else:
        for key in ("authProfileOverride", "authProfileOverrideSource", "authProfileOverrideCompactionCount"):
            if entry.pop(key, None) is not None:
                updated = True

    if updated:
        for key in ("fallbackNoticeSelectedModel", "fallbackNoticeActiveModel", "fallbackNoticeReason"):
            entry.pop(key, None)
        entry["updatedAt"] = int(time.time() * 1000)

    return updated

"""Shared entry status — ported from bk/src/shared/entry-status.ts,
entry-metadata.ts.

Entry metadata requirements evaluation with emoji/homepage resolution.
"""
from __future__ import annotations

import sys
from typing import Any, Callable

from .requirements import (
    RequirementRemote,
    RequirementsResult,
    evaluate_requirements_from_metadata_with_remote,
)


# ─── entry-metadata.ts ───

def resolve_emoji_and_homepage(
    metadata: dict[str, Any] | None = None,
    frontmatter: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    """Resolve emoji and homepage from metadata/frontmatter."""
    emoji = None
    homepage = None

    if metadata and isinstance(metadata, dict):
        if isinstance(metadata.get("emoji"), str):
            emoji = metadata["emoji"]
        if isinstance(metadata.get("homepage"), str):
            homepage = metadata["homepage"]

    if not emoji and frontmatter and isinstance(frontmatter, dict):
        if isinstance(frontmatter.get("emoji"), str):
            emoji = frontmatter["emoji"]

    if not homepage and frontmatter and isinstance(frontmatter, dict):
        for key in ("homepage", "website", "url"):
            val = frontmatter.get(key)
            if isinstance(val, str) and val.strip():
                homepage = val.strip()
                break

    return {"emoji": emoji, "homepage": homepage}


# ─── entry-status.ts ───

def evaluate_entry_metadata_requirements(
    always: bool = False,
    metadata: dict[str, Any] | None = None,
    frontmatter: dict[str, Any] | None = None,
    has_local_bin: Callable[[str], bool] = lambda _: False,
    local_platform: str = "",
    remote: RequirementRemote | None = None,
    is_env_satisfied: Callable[[str], bool] = lambda _: False,
    is_config_satisfied: Callable[[str], bool] = lambda _: False,
) -> dict[str, Any]:
    """Evaluate entry metadata requirements."""
    em = resolve_emoji_and_homepage(metadata, frontmatter)
    result = evaluate_requirements_from_metadata_with_remote(
        metadata=metadata,
        remote=remote,
        always=always,
        has_local_bin=has_local_bin,
        local_platform=local_platform or sys.platform,
        is_env_satisfied=is_env_satisfied,
        is_config_satisfied=is_config_satisfied,
    )
    out: dict[str, Any] = {}
    if em.get("emoji"):
        out["emoji"] = em["emoji"]
    if em.get("homepage"):
        out["homepage"] = em["homepage"]
    out["required"] = result.required
    out["missing"] = result.missing
    out["requirements_satisfied"] = result.eligible
    out["config_checks"] = result.config_checks
    return out


def evaluate_entry_metadata_requirements_for_current_platform(
    **kwargs: Any,
) -> dict[str, Any]:
    """Evaluate entry metadata for the current platform."""
    kwargs.setdefault("local_platform", sys.platform)
    return evaluate_entry_metadata_requirements(**kwargs)

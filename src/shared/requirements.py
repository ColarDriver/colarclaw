"""Shared requirements — ported from bk/src/shared/requirements.ts.

Requirements evaluation: binary, env, config, and OS dependency checking
with local + remote support.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Requirements:
    bins: list[str] = field(default_factory=list)
    any_bins: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    config: list[str] = field(default_factory=list)
    os: list[str] = field(default_factory=list)


@dataclass
class RequirementConfigCheck:
    path: str = ""
    satisfied: bool = False


@dataclass
class RequirementsMetadata:
    requires: dict[str, Any] | None = None
    os: list[str] | None = None


@dataclass
class RequirementRemote:
    has_bin: Callable[[str], bool] | None = None
    has_any_bin: Callable[[list[str]], bool] | None = None
    platforms: list[str] | None = None


@dataclass
class RequirementsResult:
    required: Requirements = field(default_factory=Requirements)
    missing: Requirements = field(default_factory=Requirements)
    eligible: bool = True
    config_checks: list[RequirementConfigCheck] = field(default_factory=list)


def resolve_missing_bins(
    required: list[str],
    has_local_bin: Callable[[str], bool],
    has_remote_bin: Callable[[str], bool] | None = None,
) -> list[str]:
    missing = []
    for bin_name in required:
        if has_local_bin(bin_name):
            continue
        if has_remote_bin and has_remote_bin(bin_name):
            continue
        missing.append(bin_name)
    return missing


def resolve_missing_any_bins(
    required: list[str],
    has_local_bin: Callable[[str], bool],
    has_remote_any_bin: Callable[[list[str]], bool] | None = None,
) -> list[str]:
    if not required:
        return []
    if any(has_local_bin(b) for b in required):
        return []
    if has_remote_any_bin and has_remote_any_bin(required):
        return []
    return list(required)


def resolve_missing_os(
    required: list[str],
    local_platform: str,
    remote_platforms: list[str] | None = None,
) -> list[str]:
    if not required:
        return []
    if local_platform in required:
        return []
    if remote_platforms and any(p in required for p in remote_platforms):
        return []
    return list(required)


def resolve_missing_env(
    required: list[str],
    is_satisfied: Callable[[str], bool],
) -> list[str]:
    return [name for name in required if not is_satisfied(name)]


def build_config_checks(
    required: list[str],
    is_satisfied: Callable[[str], bool],
) -> list[RequirementConfigCheck]:
    return [RequirementConfigCheck(path=p, satisfied=is_satisfied(p)) for p in required]


def evaluate_requirements(
    required: Requirements,
    always: bool = False,
    has_local_bin: Callable[[str], bool] = lambda _: False,
    has_remote_bin: Callable[[str], bool] | None = None,
    has_remote_any_bin: Callable[[list[str]], bool] | None = None,
    local_platform: str = "",
    remote_platforms: list[str] | None = None,
    is_env_satisfied: Callable[[str], bool] = lambda _: False,
    is_config_satisfied: Callable[[str], bool] = lambda _: False,
) -> RequirementsResult:
    """Evaluate full requirements."""
    missing_bins = resolve_missing_bins(required.bins, has_local_bin, has_remote_bin)
    missing_any = resolve_missing_any_bins(required.any_bins, has_local_bin, has_remote_any_bin)
    missing_os = resolve_missing_os(required.os, local_platform or sys.platform, remote_platforms)
    missing_env = resolve_missing_env(required.env, is_env_satisfied)
    config_checks = build_config_checks(required.config, is_config_satisfied)
    missing_config = [c.path for c in config_checks if not c.satisfied]

    if always:
        missing = Requirements()
    else:
        missing = Requirements(
            bins=missing_bins,
            any_bins=missing_any,
            env=missing_env,
            config=missing_config,
            os=missing_os,
        )

    eligible = always or (
        not missing.bins
        and not missing.any_bins
        and not missing.env
        and not missing.config
        and not missing.os
    )

    return RequirementsResult(
        required=required,
        missing=missing,
        eligible=eligible,
        config_checks=config_checks,
    )


def evaluate_requirements_from_metadata(
    metadata: RequirementsMetadata | dict[str, Any] | None = None,
    **kwargs: Any,
) -> RequirementsResult:
    """Evaluate requirements from metadata dict."""
    if metadata is None:
        metadata = {}
    if isinstance(metadata, dict):
        requires = metadata.get("requires", {}) or {}
        os_list = metadata.get("os", []) or []
    else:
        requires = metadata.requires or {}
        os_list = metadata.os or []

    required = Requirements(
        bins=requires.get("bins", []) if isinstance(requires, dict) else [],
        any_bins=requires.get("anyBins", []) if isinstance(requires, dict) else [],
        env=requires.get("env", []) if isinstance(requires, dict) else [],
        config=requires.get("config", []) if isinstance(requires, dict) else [],
        os=os_list,
    )
    return evaluate_requirements(required=required, **kwargs)


def evaluate_requirements_from_metadata_with_remote(
    metadata: RequirementsMetadata | dict[str, Any] | None = None,
    remote: RequirementRemote | None = None,
    **kwargs: Any,
) -> RequirementsResult:
    """Evaluate requirements with remote context."""
    return evaluate_requirements_from_metadata(
        metadata=metadata,
        has_remote_bin=remote.has_bin if remote else None,
        has_remote_any_bin=remote.has_any_bin if remote else None,
        remote_platforms=remote.platforms if remote else None,
        **kwargs,
    )

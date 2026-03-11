"""Auth profile repair — ported from bk/src/agents/auth-profiles/repair.ts.

Repairs profile ID drift and migration issues.
"""
from __future__ import annotations

from typing import Any

from .types import AuthProfileIdRepairResult, AuthProfileStore


def repair_auth_profile_ids(
    store: AuthProfileStore,
    config: Any | None = None,
) -> AuthProfileIdRepairResult:
    """Repair profile ID references that have drifted."""
    changes: list[str] = []
    migrated = False
    from_id: str | None = None
    to_id: str | None = None

    # Check for profile IDs in config that don't exist in the store
    if config and hasattr(config, "auth"):
        auth_cfg = getattr(config, "auth", None)
        if auth_cfg and hasattr(auth_cfg, "profiles"):
            cfg_profiles = getattr(auth_cfg, "profiles", {})
            if isinstance(cfg_profiles, dict):
                for cfg_pid in cfg_profiles:
                    if cfg_pid not in store.profiles:
                        # Try to find a matching profile by provider
                        cfg_provider = cfg_profiles[cfg_pid].get("provider", "") if isinstance(cfg_profiles[cfg_pid], dict) else ""
                        for store_pid, cred in store.profiles.items():
                            if getattr(cred, "provider", "") == cfg_provider and store_pid != cfg_pid:
                                changes.append(f"Migrated {cfg_pid} -> {store_pid}")
                                migrated = True
                                from_id = cfg_pid
                                to_id = store_pid
                                break

    return AuthProfileIdRepairResult(
        config=config,
        changes=changes,
        migrated=migrated,
        from_profile_id=from_id,
        to_profile_id=to_id,
    )

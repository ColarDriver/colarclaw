"""Auth profile store — ported from bk/src/agents/auth-profiles/store.ts.

Loading, saving, and merging auth profile stores.
"""
from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from typing import Any

from .constants import AUTH_STORE_VERSION, log
from .paths import ensure_auth_store_file, resolve_auth_store_path, resolve_legacy_auth_store_path
from .types import AuthProfileCredential, AuthProfileStore, ProfileUsageStats

_AUTH_PROFILE_TYPES = {"api_key", "oauth", "token"}
_runtime_store_snapshots: dict[str, AuthProfileStore] = {}


def _load_json_file(path: str) -> Any | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json_file(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _coerce_auth_store(raw: Any) -> AuthProfileStore | None:
    if not raw or not isinstance(raw, dict):
        return None
    profiles_raw = raw.get("profiles")
    if not profiles_raw or not isinstance(profiles_raw, dict):
        return None
    profiles: dict[str, AuthProfileCredential] = {}
    for key, value in profiles_raw.items():
        if not isinstance(value, dict):
            continue
        cred_type = value.get("type", value.get("mode", ""))
        if cred_type not in _AUTH_PROFILE_TYPES:
            continue
        provider = value.get("provider", "")
        if not provider:
            continue
        # Create credential based on type
        from .types import ApiKeyCredential, OAuthCredential, TokenCredential
        if cred_type == "api_key":
            profiles[key] = ApiKeyCredential(
                provider=provider, key=value.get("key") or value.get("apiKey"),
                email=value.get("email"), metadata=value.get("metadata"),
            )
        elif cred_type == "token":
            profiles[key] = TokenCredential(
                provider=provider, token=value.get("token"),
                expires=value.get("expires"), email=value.get("email"),
            )
        else:
            profiles[key] = OAuthCredential(
                provider=provider, access=value.get("access", ""),
                refresh=value.get("refresh", ""), expires=value.get("expires", 0),
                email=value.get("email"), client_id=value.get("clientId"),
            )

    order_raw = raw.get("order")
    order = None
    if isinstance(order_raw, dict):
        order = {}
        for k, v in order_raw.items():
            if isinstance(v, list):
                order[k] = [str(e) for e in v if isinstance(e, str) and e.strip()]

    return AuthProfileStore(
        version=int(raw.get("version", AUTH_STORE_VERSION)),
        profiles=profiles,
        order=order if order else None,
        last_good=raw.get("lastGood") if isinstance(raw.get("lastGood"), dict) else None,
    )


def _merge_stores(base: AuthProfileStore, override: AuthProfileStore) -> AuthProfileStore:
    merged_profiles = {**base.profiles, **override.profiles}
    return AuthProfileStore(
        version=max(base.version, override.version),
        profiles=merged_profiles,
        order={**(base.order or {}), **(override.order or {})} if (base.order or override.order) else None,
        last_good={**(base.last_good or {}), **(override.last_good or {})} if (base.last_good or override.last_good) else None,
        usage_stats={**(base.usage_stats or {}), **(override.usage_stats or {})} if (base.usage_stats or override.usage_stats) else None,
    )


def load_auth_profile_store(agent_dir: str | None = None) -> AuthProfileStore:
    auth_path = resolve_auth_store_path(agent_dir)
    raw = _load_json_file(auth_path)
    store = _coerce_auth_store(raw)
    if store:
        return store
    # Try legacy
    legacy_path = resolve_legacy_auth_store_path(agent_dir)
    legacy_raw = _load_json_file(legacy_path)
    if legacy_raw and isinstance(legacy_raw, dict):
        store = _coerce_auth_store({"version": AUTH_STORE_VERSION, "profiles": legacy_raw})
        if store:
            return store
    return AuthProfileStore()


def save_auth_profile_store(store: AuthProfileStore, agent_dir: str | None = None) -> None:
    auth_path = resolve_auth_store_path(agent_dir)
    profiles_data = {}
    for pid, cred in store.profiles.items():
        entry: dict[str, Any] = {"type": cred.type, "provider": cred.provider}
        if hasattr(cred, "key") and cred.key:
            entry["key"] = cred.key
        if hasattr(cred, "token") and cred.token:
            entry["token"] = cred.token
        if hasattr(cred, "access"):
            entry["access"] = cred.access
        if hasattr(cred, "refresh"):
            entry["refresh"] = cred.refresh
        if hasattr(cred, "expires") and cred.expires:
            entry["expires"] = cred.expires
        if hasattr(cred, "email") and cred.email:
            entry["email"] = cred.email
        profiles_data[pid] = entry

    payload: dict[str, Any] = {"version": AUTH_STORE_VERSION, "profiles": profiles_data}
    if store.order:
        payload["order"] = store.order
    if store.last_good:
        payload["lastGood"] = store.last_good
    _save_json_file(auth_path, payload)


def ensure_auth_profile_store(agent_dir: str | None = None) -> AuthProfileStore:
    return load_auth_profile_store(agent_dir)


def replace_runtime_auth_profile_store_snapshots(
    entries: list[dict[str, Any]],
) -> None:
    _runtime_store_snapshots.clear()
    for entry in entries:
        key = resolve_auth_store_path(entry.get("agent_dir"))
        _runtime_store_snapshots[key] = deepcopy(entry["store"])


def clear_runtime_auth_profile_store_snapshots() -> None:
    _runtime_store_snapshots.clear()

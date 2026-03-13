"""Shared device auth — ported from bk/src/shared/device-auth.ts,
device-auth-store.ts.

Device authentication token management and store access.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


# ─── device-auth.ts ───

@dataclass
class DeviceAuthEntry:
    token: str = ""
    role: str = ""
    scopes: list[str] = field(default_factory=list)
    updated_at_ms: int = 0


@dataclass
class DeviceAuthStore:
    version: int = 1
    device_id: str = ""
    tokens: dict[str, DeviceAuthEntry] = field(default_factory=dict)


def normalize_device_auth_role(role: str) -> str:
    return role.strip()


def normalize_device_auth_scopes(scopes: list[str] | None) -> list[str]:
    if not isinstance(scopes, list):
        return []
    return sorted({s.strip() for s in scopes if s.strip()})


# ─── device-auth-store.ts ───

class DeviceAuthStoreAdapter(Protocol):
    def read_store(self) -> DeviceAuthStore | None: ...
    def write_store(self, store: DeviceAuthStore) -> None: ...


def load_device_auth_token_from_store(
    adapter: DeviceAuthStoreAdapter,
    device_id: str,
    role: str,
) -> DeviceAuthEntry | None:
    store = adapter.read_store()
    if not store or store.device_id != device_id:
        return None
    normalized_role = normalize_device_auth_role(role)
    entry = store.tokens.get(normalized_role)
    if not entry or not entry.token:
        return None
    return entry


def store_device_auth_token_in_store(
    adapter: DeviceAuthStoreAdapter,
    device_id: str,
    role: str,
    token: str,
    scopes: list[str] | None = None,
) -> DeviceAuthEntry:
    normalized_role = normalize_device_auth_role(role)
    existing = adapter.read_store()

    next_store = DeviceAuthStore(
        version=1,
        device_id=device_id,
        tokens=dict(existing.tokens) if existing and existing.device_id == device_id else {},
    )

    entry = DeviceAuthEntry(
        token=token,
        role=normalized_role,
        scopes=normalize_device_auth_scopes(scopes),
        updated_at_ms=int(time.time() * 1000),
    )
    next_store.tokens[normalized_role] = entry
    adapter.write_store(next_store)
    return entry


def remove_device_auth_token_from_store(
    adapter: DeviceAuthStoreAdapter,
    device_id: str,
    role: str,
) -> bool:
    store = adapter.read_store()
    if not store or store.device_id != device_id:
        return False
    normalized_role = normalize_device_auth_role(role)
    if normalized_role not in store.tokens:
        return False
    del store.tokens[normalized_role]
    adapter.write_store(store)
    return True

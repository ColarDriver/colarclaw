"""Auth profiles — ported from bk/src/agents/auth-profiles.ts.

Named authentication profiles for model providers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AuthProfile:
    id: str
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    org_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

def parse_auth_profiles(config: dict[str, Any] | None = None) -> list[AuthProfile]:
    if not config:
        return []
    raw = config.get("auth", {}).get("profiles", [])
    if not isinstance(raw, list):
        return []
    profiles: list[AuthProfile] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        pid = entry.get("id", "").strip()
        provider = entry.get("provider", "").strip()
        if pid and provider:
            profiles.append(AuthProfile(
                id=pid, provider=provider,
                api_key=entry.get("apiKey"),
                base_url=entry.get("baseUrl"),
                org_id=entry.get("orgId"),
            ))
    return profiles

def find_auth_profile(profiles: list[AuthProfile], profile_id: str) -> AuthProfile | None:
    lower = profile_id.strip().lower()
    for p in profiles:
        if p.id.lower() == lower:
            return p
    return None

def find_profiles_by_provider(profiles: list[AuthProfile], provider: str) -> list[AuthProfile]:
    lower = provider.strip().lower()
    return [p for p in profiles if p.provider.lower() == lower]

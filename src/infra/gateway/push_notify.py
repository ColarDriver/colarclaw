"""Infra push notify — ported from bk/src/infra/push-apns.ts, skills-remote.ts.

APNS push notifications, remote skills fetching.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("infra.push_notify")


# ─── push-apns.ts ───

@dataclass
class ApnsConfig:
    key_id: str = ""
    team_id: str = ""
    key_path: str = ""
    bundle_id: str = ""
    production: bool = False


@dataclass
class ApnsPayload:
    alert: str | dict[str, Any] = ""
    badge: int | None = None
    sound: str | None = None
    category: str | None = None
    thread_id: str | None = None
    content_available: bool = False
    mutable_content: bool = False
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApnsResult:
    success: bool = False
    device_token: str = ""
    apns_id: str | None = None
    status_code: int = 0
    error: str | None = None


def build_apns_payload(
    alert: str | dict[str, Any] = "",
    badge: int | None = None,
    sound: str | None = None,
    category: str | None = None,
    thread_id: str | None = None,
    content_available: bool = False,
    mutable_content: bool = False,
    custom: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build APNS JSON payload."""
    aps: dict[str, Any] = {}
    if alert:
        aps["alert"] = alert
    if badge is not None:
        aps["badge"] = badge
    if sound:
        aps["sound"] = sound
    if category:
        aps["category"] = category
    if thread_id:
        aps["thread-id"] = thread_id
    if content_available:
        aps["content-available"] = 1
    if mutable_content:
        aps["mutable-content"] = 1
    payload: dict[str, Any] = {"aps": aps}
    if custom:
        payload.update(custom)
    return payload


def build_apns_jwt(config: ApnsConfig) -> str | None:
    """Build JWT for APNS authentication."""
    try:
        import jwt
        now = int(time.time())
        headers = {"alg": "ES256", "kid": config.key_id}
        claims = {"iss": config.team_id, "iat": now}
        with open(config.key_path, "r") as f:
            key = f.read()
        return jwt.encode(claims, key, algorithm="ES256", headers=headers)
    except Exception as e:
        logger.error(f"APNS JWT build failed: {e}")
        return None


async def send_apns_notification(
    device_token: str,
    payload: dict[str, Any],
    config: ApnsConfig,
) -> ApnsResult:
    """Send an APNS push notification."""
    token = build_apns_jwt(config)
    if not token:
        return ApnsResult(device_token=device_token, error="JWT build failed")

    host = "api.push.apple.com" if config.production else "api.sandbox.push.apple.com"
    url = f"https://{host}/3/device/{device_token}"

    try:
        from ..network.core import fetch_with_timeout
        result = await fetch_with_timeout(
            url,
            method="POST",
            headers={
                "authorization": f"bearer {token}",
                "apns-topic": config.bundle_id,
                "content-type": "application/json",
            },
            body=json.dumps(payload).encode(),
            timeout_s=30.0,
        )
        status = result.get("status", 0)
        return ApnsResult(
            success=status == 200,
            device_token=device_token,
            apns_id=result.get("headers", {}).get("apns-id"),
            status_code=status,
            error=None if status == 200 else f"HTTP {status}",
        )
    except Exception as e:
        return ApnsResult(device_token=device_token, error=str(e))


# ─── skills-remote.ts ───

@dataclass
class RemoteSkill:
    name: str = ""
    description: str = ""
    url: str = ""
    version: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class RemoteSkillsIndex:
    skills: list[RemoteSkill] = field(default_factory=list)
    updated_at: float = 0.0
    error: str | None = None


_skills_cache: RemoteSkillsIndex | None = None
_skills_cache_ttl_s = 300.0
_skills_cache_at = 0.0


async def fetch_remote_skills_index(
    url: str = "https://openclaw.ai/skills/index.json",
    timeout_s: float = 10.0,
    force: bool = False,
) -> RemoteSkillsIndex:
    """Fetch remote skills index with caching."""
    global _skills_cache, _skills_cache_at

    if not force and _skills_cache and time.time() - _skills_cache_at < _skills_cache_ttl_s:
        return _skills_cache

    try:
        from ..network.core import fetch_with_timeout
        result = await fetch_with_timeout(url, timeout_s=timeout_s)
        if not result.get("ok"):
            return RemoteSkillsIndex(error=f"HTTP {result.get('status', 0)}")
        body = result.get("body", b"")
        data = json.loads(body if isinstance(body, str) else body.decode(errors="replace"))
        skills = []
        for item in data.get("skills", []):
            skills.append(RemoteSkill(
                name=item.get("name", ""),
                description=item.get("description", ""),
                url=item.get("url", ""),
                version=item.get("version", ""),
                author=item.get("author", ""),
                tags=item.get("tags", []),
            ))
        index = RemoteSkillsIndex(skills=skills, updated_at=time.time())
        _skills_cache = index
        _skills_cache_at = time.time()
        return index
    except Exception as e:
        return RemoteSkillsIndex(error=str(e))


async def search_remote_skills(
    query: str,
    url: str = "https://openclaw.ai/skills/index.json",
) -> list[RemoteSkill]:
    """Search remote skills by name/description/tags."""
    index = await fetch_remote_skills_index(url=url)
    if not index.skills:
        return []
    q = query.lower()
    results: list[RemoteSkill] = []
    for skill in index.skills:
        if (q in skill.name.lower() or
            q in skill.description.lower() or
            any(q in tag.lower() for tag in skill.tags)):
            results.append(skill)
    return results

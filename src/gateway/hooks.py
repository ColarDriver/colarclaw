"""Gateway hooks — ported from bk/src/gateway/hooks.ts, hooks-mapping.ts, server/hooks.ts.

Lifecycle hooks: webhook execution, hook mapping, hook request handling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ─── hooks.ts — Hook configuration types ───

@dataclass
class HookDefinition:
    """A single hook definition."""
    url: str = ""
    events: list[str] = field(default_factory=list)
    secret: str | None = None
    timeout_ms: int = 10_000
    retry_count: int = 0
    retry_delay_ms: int = 1_000
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    method: str = "POST"


@dataclass
class HooksConfigResolved:
    """Resolved hooks configuration."""
    hooks: list[HookDefinition] = field(default_factory=list)
    enabled: bool = False


def resolve_hooks_config(cfg: dict[str, Any]) -> HooksConfigResolved:
    """Resolve hooks configuration from gateway config."""
    hooks_cfg = cfg.get("gateway", {}).get("hooks", {})
    if not hooks_cfg:
        return HooksConfigResolved()

    enabled = hooks_cfg.get("enabled", False)
    raw_hooks = hooks_cfg.get("hooks", [])
    if not isinstance(raw_hooks, list):
        return HooksConfigResolved(enabled=enabled)

    hooks: list[HookDefinition] = []
    for raw in raw_hooks:
        if not isinstance(raw, dict):
            continue
        url = raw.get("url", "").strip()
        if not url:
            continue
        events = raw.get("events", [])
        if not isinstance(events, list):
            events = []
        hooks.append(HookDefinition(
            url=url,
            events=[e.strip() for e in events if isinstance(e, str) and e.strip()],
            secret=raw.get("secret"),
            timeout_ms=int(raw.get("timeoutMs", 10_000)),
            retry_count=int(raw.get("retryCount", 0)),
            retry_delay_ms=int(raw.get("retryDelayMs", 1_000)),
            headers=raw.get("headers", {}),
            enabled=raw.get("enabled", True),
            method=raw.get("method", "POST").upper(),
        ))

    return HooksConfigResolved(hooks=hooks, enabled=enabled)


# ─── hooks-mapping.ts — Event to hook mapping ───

# Standard gateway hook events
HOOK_EVENTS = {
    "message.received",
    "message.sent",
    "session.created",
    "session.updated",
    "session.deleted",
    "agent.run.start",
    "agent.run.end",
    "agent.run.error",
    "channel.connected",
    "channel.disconnected",
    "channel.error",
    "config.changed",
    "gateway.started",
    "gateway.stopping",
    "cron.triggered",
    "cron.completed",
}


def find_hooks_for_event(
    event: str,
    hooks: list[HookDefinition],
) -> list[HookDefinition]:
    """Find all hooks that should be triggered for a given event."""
    matched: list[HookDefinition] = []
    for hook in hooks:
        if not hook.enabled:
            continue
        if not hook.events:
            # No event filter = match all events
            matched.append(hook)
            continue
        for pattern in hook.events:
            if pattern == "*":
                matched.append(hook)
                break
            if pattern == event:
                matched.append(hook)
                break
            # Wildcard matching: "message.*" matches "message.received"
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event.startswith(prefix + "."):
                    matched.append(hook)
                    break
    return matched


# ─── Hook payload construction ───

@dataclass
class HookPayload:
    """Payload sent to a hook endpoint."""
    event: str = ""
    timestamp_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    gateway_id: str = ""


def build_hook_payload(
    event: str,
    data: dict[str, Any] | None = None,
    *,
    gateway_id: str = "",
) -> dict[str, Any]:
    """Build a hook payload dict for serialization."""
    return {
        "event": event,
        "timestampMs": int(time.time() * 1000),
        "data": data or {},
        "gatewayId": gateway_id,
    }


# ─── Hook signing (HMAC) ───

def sign_hook_payload(payload: str, secret: str) -> str:
    """Sign a hook payload with HMAC-SHA256."""
    import hashlib
    import hmac
    sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={sig}"


# ─── Hook delivery ───

async def deliver_hook(
    hook: HookDefinition,
    payload: dict[str, Any],
) -> bool:
    """Deliver a hook payload to a webhook URL.

    Returns True on success, False on failure.
    """
    import aiohttp

    body = json.dumps(payload)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "OpenClaw-Gateway/1.0",
        **hook.headers,
    }

    if hook.secret:
        headers["X-OpenClaw-Signature"] = sign_hook_payload(body, hook.secret)

    timeout = aiohttp.ClientTimeout(total=hook.timeout_ms / 1000)

    for attempt in range(1 + hook.retry_count):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    hook.method,
                    hook.url,
                    data=body,
                    headers=headers,
                ) as resp:
                    if 200 <= resp.status < 300:
                        return True
                    logger.warning(
                        f"hook delivery failed: {hook.url} returned {resp.status} "
                        f"(attempt {attempt + 1}/{1 + hook.retry_count})"
                    )
        except Exception as e:
            logger.warning(
                f"hook delivery error: {hook.url} — {e} "
                f"(attempt {attempt + 1}/{1 + hook.retry_count})"
            )

        if attempt < hook.retry_count:
            await asyncio.sleep(hook.retry_delay_ms / 1000)

    return False


async def dispatch_hooks(
    event: str,
    data: dict[str, Any] | None,
    hooks_config: HooksConfigResolved,
    *,
    gateway_id: str = "",
) -> None:
    """Dispatch a hook event to all matching hooks."""
    if not hooks_config.enabled or not hooks_config.hooks:
        return

    matched = find_hooks_for_event(event, hooks_config.hooks)
    if not matched:
        return

    payload = build_hook_payload(event, data, gateway_id=gateway_id)

    # Fire all hooks concurrently
    tasks = [deliver_hook(hook, payload) for hook in matched]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"hook dispatch error for {matched[i].url}: {result}")

"""Channels thread_bindings — ported from bk/src/channels/thread-bindings-policy.ts,
thread-binding-id.ts, thread-bindings-messages.ts.

Thread binding resolution, spawn policy, idle/max-age timeout configuration,
and session-to-thread ID mapping.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal


# ─── constants ───

DISCORD_THREAD_BINDING_CHANNEL = "discord"
DEFAULT_THREAD_BINDING_IDLE_HOURS = 24
DEFAULT_THREAD_BINDING_MAX_AGE_HOURS = 0

ThreadBindingSpawnKind = Literal["subagent", "acp"]


# ─── types ───

@dataclass
class ThreadBindingSpawnPolicy:
    channel: str = ""
    account_id: str = ""
    enabled: bool = True
    spawn_enabled: bool = True


# ─── thread-binding-id.ts ───

def build_thread_binding_id(channel: str, target: str, thread_id: str) -> str:
    """Build a stable thread binding ID."""
    raw = f"{channel}:{target}:{thread_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ─── normalization helpers ───

def _normalize_channel_id(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_account_id(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _normalize_hours(raw: Any) -> float | None:
    if not isinstance(raw, (int, float)):
        return None
    if raw < 0 or not (raw == raw):  # NaN check
        return None
    return float(raw)


# ─── timeout resolution ───

def resolve_thread_binding_idle_timeout_ms(
    channel_idle_hours_raw: Any = None,
    session_idle_hours_raw: Any = None,
) -> int:
    """Resolve idle timeout in ms for thread bindings."""
    hours = (
        _normalize_hours(channel_idle_hours_raw)
        or _normalize_hours(session_idle_hours_raw)
        or DEFAULT_THREAD_BINDING_IDLE_HOURS
    )
    return int(hours * 60 * 60 * 1000)


def resolve_thread_binding_max_age_ms(
    channel_max_age_hours_raw: Any = None,
    session_max_age_hours_raw: Any = None,
) -> int:
    """Resolve max age in ms for thread bindings."""
    hours = (
        _normalize_hours(channel_max_age_hours_raw)
        or _normalize_hours(session_max_age_hours_raw)
        or DEFAULT_THREAD_BINDING_MAX_AGE_HOURS
    )
    return int(hours * 60 * 60 * 1000)


def resolve_thread_bindings_enabled(
    channel_enabled_raw: Any = None,
    session_enabled_raw: Any = None,
) -> bool:
    """Resolve whether thread bindings are enabled."""
    result = _normalize_boolean(channel_enabled_raw)
    if result is not None:
        return result
    result = _normalize_boolean(session_enabled_raw)
    if result is not None:
        return result
    return True


# ─── spawn policy ───

def resolve_thread_binding_spawn_policy(
    cfg: dict[str, Any],
    channel: str,
    kind: ThreadBindingSpawnKind,
    account_id: str | None = None,
) -> ThreadBindingSpawnPolicy:
    """Resolve thread binding spawn policy from config."""
    ch = _normalize_channel_id(channel)
    acct = _normalize_account_id(account_id)

    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(ch, {})
    account_cfg = channel_cfg.get("accounts", {}).get(acct, {}) if acct else {}

    root_tb = channel_cfg.get("threadBindings", {})
    account_tb = account_cfg.get("threadBindings", {}) if account_cfg else {}

    session_tb = cfg.get("session", {}).get("threadBindings", {})

    enabled = (
        _normalize_boolean(account_tb.get("enabled"))
        or _normalize_boolean(root_tb.get("enabled"))
        or _normalize_boolean(session_tb.get("enabled"))
    )
    if enabled is None:
        enabled = True

    spawn_flag = "spawnSubagentSessions" if kind == "subagent" else "spawnAcpSessions"
    spawn_raw = _normalize_boolean(account_tb.get(spawn_flag)) or _normalize_boolean(root_tb.get(spawn_flag))
    spawn_enabled = spawn_raw if spawn_raw is not None else (ch != DISCORD_THREAD_BINDING_CHANNEL)

    return ThreadBindingSpawnPolicy(
        channel=ch, account_id=acct,
        enabled=enabled, spawn_enabled=spawn_enabled,
    )


# ─── error formatting ───

def format_thread_binding_disabled_error(channel: str, kind: ThreadBindingSpawnKind) -> str:
    if channel == DISCORD_THREAD_BINDING_CHANNEL:
        return "Discord thread bindings are disabled (set channels.discord.threadBindings.enabled=true)."
    return f"Thread bindings are disabled for {channel} (set session.threadBindings.enabled=true)."


def format_thread_binding_spawn_disabled_error(
    channel: str, kind: ThreadBindingSpawnKind,
) -> str:
    if channel == DISCORD_THREAD_BINDING_CHANNEL and kind == "acp":
        return "Discord thread-bound ACP spawns are disabled (set channels.discord.threadBindings.spawnAcpSessions=true)."
    if channel == DISCORD_THREAD_BINDING_CHANNEL and kind == "subagent":
        return "Discord thread-bound subagent spawns are disabled (set channels.discord.threadBindings.spawnSubagentSessions=true)."
    return f"Thread-bound {kind} spawns are disabled for {channel}."

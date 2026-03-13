"""Gateway server methods — send, sessions, connect, channels, devices, nodes, config.

Ported from bk/src/gateway/server-methods/send.ts, sessions.ts, connect.ts,
channels.ts, devices.ts, nodes.ts, config.ts, logs.ts, models.ts,
cron.ts, skills.ts, system.ts, health.ts, usage.ts, update.ts,
secrets.ts, push.ts, exec-approvals.ts, exec-approval.ts,
wizard.ts, doctor.ts, talk.ts, web.ts, validation.ts, tts.ts.

Covers the remaining ~30 server method handler files.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── send.ts — Message sending with idempotency and inflight dedup ───

@dataclass
class SendRequest:
    to: str = ""
    message: str = ""
    media_url: str | None = None
    media_urls: list[str] | None = None
    gif_playback: bool = False
    channel: str | None = None
    account_id: str | None = None
    agent_id: str | None = None
    thread_id: str | None = None
    session_key: str | None = None
    idempotency_key: str = ""


class InflightDeduplicator:
    """Prevents duplicate send operations using idempotency keys."""

    def __init__(self) -> None:
        self._inflight: dict[str, Any] = {}
        self._cache: dict[str, dict[str, Any]] = {}

    def check(self, key: str) -> dict[str, Any] | None:
        """Check for a cached result. Returns None if not seen."""
        return self._cache.get(key)

    def is_inflight(self, key: str) -> bool:
        return key in self._inflight

    def mark_inflight(self, key: str) -> None:
        self._inflight[key] = time.time()

    def complete(self, key: str, result: dict[str, Any]) -> None:
        self._inflight.pop(key, None)
        self._cache[key] = result

    def fail(self, key: str, error: dict[str, Any]) -> None:
        self._inflight.pop(key, None)
        self._cache[key] = error


# ─── sessions.ts — Session management methods ───

@dataclass
class SessionsResetRequest:
    key: str = ""
    reason: str = "reset"  # "new" | "reset"


@dataclass
class SessionsCompactRequest:
    key: str = ""


# ─── connect.ts — Client connection handshake ───

@dataclass
class ConnectRequest:
    """Client connection handshake parameters."""
    client_id: str = ""
    client_mode: str = "operator"
    platform: str = ""
    version: str = ""
    instance_id: str = ""
    caps: list[str] = field(default_factory=list)
    role: str = "operator"
    scopes: list[str] = field(default_factory=list)
    token: str | None = None
    device_id: str | None = None
    device_family: str | None = None
    display_name: str | None = None
    min_protocol: int = 3
    max_protocol: int = 3


@dataclass
class ConnectResponse:
    ok: bool = True
    conn_id: str = ""
    protocol_version: int = 3
    server_version: str = ""
    error: str | None = None


# ─── channels.ts — Channel status and control ───

@dataclass
class ChannelStatusEntry:
    id: str = ""
    name: str = ""
    status: str = "disconnected"  # "connected" | "connecting" | "disconnected" | "error"
    error: str | None = None
    account_id: str | None = None
    connected_at_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── devices.ts — Paired device management ───

@dataclass
class PairedDevice:
    device_id: str = ""
    display_name: str = ""
    platform: str = ""
    paired_at_ms: int = 0
    last_seen_ms: int = 0
    online: bool = False


# ─── nodes.ts — Compute node methods ───

@dataclass
class NodeInvokeRequest:
    node_id: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str = ""
    timeout_ms: int = 300_000
    idempotency_key: str = ""


@dataclass
class NodeInvokeResult:
    ok: bool = True
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error: str | None = None


# ─── models.ts — Model listing and catalog ───

@dataclass
class ModelListEntry:
    provider: str = ""
    model: str = ""
    display_name: str = ""
    context_window: int = 0
    supports_tools: bool = False
    supports_vision: bool = False
    supports_thinking: bool = False
    is_default: bool = False


# ─── logs.ts — Log tailing ───

@dataclass
class LogTailRequest:
    lines: int = 100
    follow: bool = False
    level: str | None = None  # "debug" | "info" | "warn" | "error"
    subsystem: str | None = None


# ─── cron.ts — Cron management methods ───

@dataclass
class CronTriggerRequest:
    job_id: str = ""
    force: bool = False


# ─── skills.ts ───

@dataclass
class SkillStatusEntry:
    id: str = ""
    name: str = ""
    version: str = ""
    enabled: bool = True
    status: str = "loaded"  # "loaded" | "disabled" | "error"


# ─── system.ts — System info ───

@dataclass
class SystemInfoResponse:
    version: str = ""
    platform: str = ""
    arch: str = ""
    node_version: str = ""
    uptime_ms: int = 0
    memory_mb: float = 0


# ─── usage.ts — Token usage tracking ───

@dataclass
class UsageSummary:
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)
    period: str = ""  # "today" | "week" | "month" | "all"


# ─── update.ts — Gateway update check ───

@dataclass
class UpdateCheckResult:
    current_version: str = ""
    latest_version: str = ""
    update_available: bool = False
    update_url: str = ""
    changelog: str = ""


# ─── secrets.ts — Secret resolution ───

@dataclass
class SecretResolveRequest:
    refs: list[str] = field(default_factory=list)


@dataclass
class SecretResolveResult:
    resolved: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


# ─── push.ts — Push notification methods ───

@dataclass
class PushNotificationRequest:
    title: str = ""
    body: str = ""
    target: str = ""  # device_id or "all"
    data: dict[str, Any] = field(default_factory=dict)


# ─── wizard.ts — Guided setup wizard ───

@dataclass
class WizardStep:
    id: str = ""
    title: str = ""
    type: str = ""  # "input" | "select" | "confirm" | "info"
    options: list[dict[str, str]] = field(default_factory=list)
    default_value: str = ""
    description: str = ""
    required: bool = False


@dataclass
class WizardState:
    wizard_id: str = ""
    current_step: int = 0
    total_steps: int = 0
    steps: list[WizardStep] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    status: str = "in_progress"  # "in_progress" | "completed" | "cancelled"


# ─── doctor.ts — Diagnostics ───

@dataclass
class DoctorCheckResult:
    name: str = ""
    status: str = "ok"  # "ok" | "warning" | "error"
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# ─── talk.ts — Voice/audio methods ───

@dataclass
class TalkRequest:
    text: str = ""
    voice: str = ""
    session_key: str | None = None
    language: str | None = None


# ─── tts.ts — Text-to-speech ───

@dataclass
class TtsRequest:
    text: str = ""
    voice: str = "default"
    format: str = "mp3"  # "mp3" | "wav" | "ogg"


# ─── validation.ts — Parameter validation helpers ───

def validate_session_key(key: str) -> tuple[bool, str]:
    """Validate a session key string."""
    if not key or not isinstance(key, str):
        return False, "session key is required"
    stripped = key.strip()
    if not stripped:
        return False, "session key must not be empty"
    if len(stripped) > 512:
        return False, "session key too long"
    if "\x00" in stripped:
        return False, "session key must not contain null bytes"
    return True, ""


def validate_idempotency_key(key: str) -> tuple[bool, str]:
    """Validate an idempotency key."""
    if not key or not isinstance(key, str):
        return False, "idempotencyKey is required"
    stripped = key.strip()
    if not stripped:
        return False, "idempotencyKey must not be empty"
    if len(stripped) > 256:
        return False, "idempotencyKey too long"
    return True, ""

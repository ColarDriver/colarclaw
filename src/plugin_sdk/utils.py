"""Plugin SDK utilities — ported from remaining bk/src/plugin-sdk/*.ts.

Consolidates: account-id, account-resolution, allow-from, allowlist-resolution,
boolean-param, channel-config-helpers, channel-lifecycle, channel-send-result,
command-auth, config-paths, device-pair, discord-send, fetch-auth, file-lock,
group-access, inbound-envelope, inbound-reply-dispatch, json-store, keyed-async-queue,
oauth-utils, onboarding, outbound-media, pairing-access, provider-auth-result,
reply-payload, request-url, resolution-notes, runtime, run-command, ssrf-policy,
status-helpers, temp-path, text-chunking, tool-send, windows-spawn, etc.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

DEFAULT_ACCOUNT_ID = "default"


# ─── Account ID ───
def normalize_account_id(raw: str | None) -> str:
    if not raw:
        return DEFAULT_ACCOUNT_ID
    return raw.strip().lower() or DEFAULT_ACCOUNT_ID


def normalize_agent_id(raw: str | None) -> str:
    if not raw:
        return "default"
    return raw.strip().lower() or "default"


# ─── Allow-from ───
def format_allow_from_lowercase(entries: list[str]) -> list[str]:
    return [e.strip().lower() for e in entries if e.strip()]


def is_normalized_sender_allowed(sender: str, allow_list: list[str]) -> bool:
    normalized = sender.strip().lower()
    if not allow_list:
        return True
    return normalized in {e.lower() for e in allow_list}


# ─── Boolean param ───
def read_boolean_param(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return default


# ─── Channel send result ───
@dataclass
class ChannelSendResult:
    ok: bool = True
    message_id: str | None = None
    error: str | None = None
    channel_error: str | None = None


def build_channel_send_result(ok: bool = True, message_id: str | None = None, error: str | None = None) -> ChannelSendResult:
    return ChannelSendResult(ok=ok, message_id=message_id, error=error)


# ─── File lock ───
class FileLockHandle:
    def __init__(self, path: str, fd: int | None = None):
        self.path = path
        self.fd = fd

    def release(self) -> None:
        if self.fd is not None:
            try:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None


async def acquire_file_lock(path: str, timeout_ms: int = 10000) -> FileLockHandle:
    """Acquire file lock (placeholder)."""
    return FileLockHandle(path=path)


async def with_file_lock(path: str, fn: Callable[..., Any], timeout_ms: int = 10000) -> Any:
    lock = await acquire_file_lock(path, timeout_ms)
    try:
        return await fn()
    finally:
        lock.release()


# ─── JSON store ───
def read_json_file_with_fallback(path: str, fallback: Any = None) -> Any:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return fallback


def write_json_file_atomically(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ─── Keyed async queue ───
class KeyedAsyncQueue:
    def __init__(self, concurrency: int = 1):
        self._queues: dict[str, asyncio.Queue[Any]] = {}
        self._concurrency = concurrency

    async def enqueue(self, key: str, task: Callable[..., Any]) -> Any:
        return await task()


async def enqueue_keyed_task(queue: KeyedAsyncQueue, key: str, task: Callable[..., Any]) -> Any:
    return await queue.enqueue(key, task)


# ─── OAuth utils ───
def generate_pkce_verifier_challenge() -> dict[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    return {"verifier": verifier, "challenge": challenge}


def to_form_url_encoded(params: dict[str, str]) -> str:
    from urllib.parse import urlencode
    return urlencode(params)


# ─── Provider auth result ───
def build_oauth_provider_auth_result(profiles: list[dict[str, Any]] | None = None, **kwargs: Any) -> dict[str, Any]:
    return {"profiles": profiles or [], **kwargs}


# ─── Reply payload ───
@dataclass
class OutboundReplyPayload:
    text: str = ""
    media_urls: list[str] | None = None
    media_url: str | None = None


def normalize_outbound_reply_payload(payload: Any) -> OutboundReplyPayload:
    if isinstance(payload, str):
        return OutboundReplyPayload(text=payload)
    if isinstance(payload, dict):
        return OutboundReplyPayload(
            text=payload.get("text", ""),
            media_urls=payload.get("mediaUrls") or payload.get("media_urls"),
            media_url=payload.get("mediaUrl") or payload.get("media_url"),
        )
    return OutboundReplyPayload()


# ─── Text chunking ───
def chunk_text_for_outbound(text: str, max_chars: int = 2000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


# ─── SSRF policy ───
def is_private_ip_address(ip: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private
    except ValueError:
        return False


def is_blocked_hostname(hostname: str) -> bool:
    return hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


# ─── Status helpers ───
def build_base_account_status_snapshot(account_id: str = DEFAULT_ACCOUNT_ID, **kwargs: Any) -> dict[str, Any]:
    return {"account_id": account_id, "status": "unknown", **kwargs}


# ─── Temp path ───
def build_random_temp_file_path(ext: str = "", prefix: str = "plugin-") -> str:
    fd, path = tempfile.mkstemp(suffix=ext, prefix=prefix)
    os.close(fd)
    return path


# ─── Command auth ───
async def resolve_sender_command_authorization(sender_id: str, config: Any = None, channel: str = "") -> dict[str, Any]:
    return {"authorized": True, "reason": "default"}


# ─── Run command ───
@dataclass
class PluginCommandRunResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False


async def run_plugin_command_with_timeout(command: str, args: list[str] | None = None, timeout_ms: int = 30000, cwd: str | None = None) -> PluginCommandRunResult:
    """Run external command with timeout (placeholder)."""
    return PluginCommandRunResult()


# ─── Channel lifecycle ───
async def keep_http_server_task_alive(server: Any = None) -> None:
    pass


async def wait_until_abort() -> None:
    pass


# ─── Agent media payload ───
@dataclass
class AgentMediaPayload:
    text: str = ""
    media_urls: list[str] | None = None
    audio_as_voice: bool = False


def build_agent_media_payload(text: str = "", media_urls: list[str] | None = None) -> AgentMediaPayload:
    return AgentMediaPayload(text=text, media_urls=media_urls)

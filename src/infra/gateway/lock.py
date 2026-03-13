"""Infra gateway_lock — ported from bk/src/infra/gateway-lock.ts,
jsonl-socket.ts, json-utf8-bytes.ts, prototype-keys.ts.

Gateway process locking (single-instance enforcement), JSONL socket
communication, JSON byte counting, prototype key guards.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import socket
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger("infra.gateway_lock")

T = TypeVar("T")


# ─── prototype-keys.ts ───

_BLOCKED_OBJECT_KEYS = {"__proto__", "prototype", "constructor"}


def is_blocked_object_key(key: str) -> bool:
    return key in _BLOCKED_OBJECT_KEYS


# ─── json-utf8-bytes.ts ───

def json_utf8_bytes(value: Any) -> int:
    """Return the UTF-8 byte length of a JSON-serialized value."""
    try:
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return len(str(value).encode("utf-8"))


# ─── jsonl-socket.ts ───

async def request_jsonl_socket(
    socket_path: str,
    payload: str,
    timeout_ms: float = 5000,
    accept: Callable[[Any], T | None] | None = None,
) -> T | None:
    """Send a JSONL payload over a Unix socket and read responses."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(socket_path),
            timeout=timeout_ms / 1000.0,
        )
    except (asyncio.TimeoutError, OSError):
        return None

    try:
        writer.write(f"{payload}\n".encode("utf-8"))
        await writer.drain()

        buffer = ""
        while True:
            try:
                data = await asyncio.wait_for(
                    reader.read(4096),
                    timeout=timeout_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                return None
            if not data:
                return None
            buffer += data.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if accept:
                        result = accept(msg)
                        if result is not None:
                            return result
                except json.JSONDecodeError:
                    pass
    except Exception:
        return None
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


# ─── gateway-lock.ts ───

DEFAULT_TIMEOUT_MS = 5000
DEFAULT_POLL_INTERVAL_MS = 0.1  # seconds
DEFAULT_STALE_S = 30.0
DEFAULT_PORT_PROBE_TIMEOUT_S = 1.0


class GatewayLockError(Exception):
    pass


@dataclass
class LockPayload:
    pid: int = 0
    created_at: str = ""
    config_path: str = ""
    start_time: int | None = None


@dataclass
class GatewayLockHandle:
    lock_path: str = ""
    config_path: str = ""
    _fd: int | None = None

    async def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it


def _check_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is free (no listener)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(DEFAULT_PORT_PROBE_TIMEOUT_S)
    try:
        sock.connect((host, port))
        sock.close()
        return False  # Connection succeeded -> port in use
    except (ConnectionRefusedError, socket.timeout, OSError):
        return True  # Port is free
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _read_linux_cmdline(pid: int) -> list[str] | None:
    try:
        with open(f"/proc/{pid}/cmdline", "r") as f:
            raw = f.read()
        return [p.strip() for p in raw.split("\0") if p.strip()]
    except OSError:
        return None


def _read_linux_start_time(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            raw = f.read().strip()
        close_paren = raw.rfind(")")
        if close_paren < 0:
            return None
        rest = raw[close_paren + 1:].strip()
        fields = rest.split()
        if len(fields) > 19:
            return int(fields[19])
        return None
    except (OSError, ValueError, IndexError):
        return None


def _is_gateway_argv(args: list[str]) -> bool:
    normalized = [a.replace("\\", "/").lower() for a in args]
    if "gateway" not in normalized:
        return False
    entry_candidates = [
        "dist/index.js", "dist/entry.js", "openclaw.mjs",
        "scripts/run-node.mjs", "src/index.ts",
    ]
    if any(a.endswith(e) for a in normalized for e in entry_candidates):
        return True
    exe = normalized[0] if normalized else ""
    return exe.endswith("/openclaw") or exe == "openclaw"


def _resolve_owner_status(pid: int, payload: LockPayload | None, port: int | None = None) -> str:
    """Returns 'alive', 'dead', or 'unknown'."""
    if port is not None:
        if _check_port_free(port):
            return "dead"

    if not _is_pid_alive(pid):
        return "dead"

    if sys.platform != "linux":
        return "alive"

    if payload and payload.start_time is not None:
        current_st = _read_linux_start_time(pid)
        if current_st is None:
            return "unknown"
        return "alive" if current_st == payload.start_time else "dead"

    args = _read_linux_cmdline(pid)
    if not args:
        return "unknown"
    return "alive" if _is_gateway_argv(args) else "dead"


def _read_lock_payload(lock_path: str) -> LockPayload | None:
    try:
        with open(lock_path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "pid" not in data:
            return None
        return LockPayload(
            pid=int(data["pid"]),
            created_at=str(data.get("createdAt", "")),
            config_path=str(data.get("configPath", "")),
            start_time=data.get("startTime"),
        )
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _resolve_lock_path(
    state_dir: str | None = None,
    config_path: str | None = None,
) -> tuple[str, str]:
    s_dir = state_dir or os.path.join(str(Path.home()), ".openclaw", "state")
    c_path = config_path or os.path.join(str(Path.home()), ".openclaw", "config.json")
    h = hashlib.sha256(c_path.encode()).hexdigest()[:8]
    lock_dir = os.path.join(s_dir, "locks")
    lock_path = os.path.join(lock_dir, f"gateway.{h}.lock")
    return lock_path, c_path


async def acquire_gateway_lock(
    state_dir: str | None = None,
    config_path: str | None = None,
    timeout_s: float = 5.0,
    poll_interval_s: float = 0.1,
    stale_s: float = 30.0,
    port: int | None = None,
) -> GatewayLockHandle | None:
    """Try to acquire the gateway lock. Returns None if skipped, raises on timeout."""
    if os.environ.get("OPENCLAW_ALLOW_MULTI_GATEWAY") == "1":
        return None

    lock_path, c_path = _resolve_lock_path(state_dir, config_path)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    start = time.monotonic()
    last_payload: LockPayload | None = None

    while time.monotonic() - start < timeout_s:
        try:
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            start_time = _read_linux_start_time(os.getpid()) if sys.platform == "linux" else None
            payload = {
                "pid": os.getpid(),
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "configPath": c_path,
            }
            if start_time is not None:
                payload["startTime"] = start_time
            os.write(fd, json.dumps(payload).encode("utf-8"))
            return GatewayLockHandle(lock_path=lock_path, config_path=c_path, _fd=fd)

        except FileExistsError:
            last_payload = _read_lock_payload(lock_path)
            owner_pid = last_payload.pid if last_payload else None

            if owner_pid:
                status = _resolve_owner_status(owner_pid, last_payload, port)
                if status == "dead":
                    try:
                        os.unlink(lock_path)
                    except OSError:
                        pass
                    continue

            # Check staleness
            try:
                st = os.stat(lock_path)
                age_s = time.time() - st.st_mtime
                if age_s > stale_s:
                    os.unlink(lock_path)
                    continue
            except OSError:
                pass

            await asyncio.sleep(poll_interval_s)

        except OSError as e:
            raise GatewayLockError(f"Failed to acquire gateway lock at {lock_path}") from e

    owner = f" (pid {last_payload.pid})" if last_payload else ""
    raise GatewayLockError(
        f"Gateway already running{owner}; lock timeout after {timeout_s}s"
    )

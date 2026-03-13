"""Infra tailscale — ported from bk/src/infra/tailscale.ts, tailnet.ts,
widearea-dns.ts.

Tailscale integration: binary discovery, status queries, whois identity,
funnel/serve management, tailnet hostname resolution, wide-area DNS.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("infra.tailscale")


# ─── tailscale binary detection ───

_cached_tailscale_binary: str | None = None


async def _run_exec(cmd: str, args: list[str], timeout_s: float = 5.0,
                     max_buffer: int = 200_000) -> tuple[str, str]:
    """Run a command and return (stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        cmd, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        proc.communicate(), timeout=timeout_s,
    )
    stdout = stdout_bytes.decode(errors="replace")[:max_buffer]
    stderr = stderr_bytes.decode(errors="replace")[:max_buffer]
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd} {' '.join(args)}: {stderr.strip()}")
    return stdout, stderr


async def _check_binary(path: str) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        await asyncio.wait_for(
            _run_exec(path, ["--version"], timeout_s=3.0),
            timeout=3.0,
        )
        return True
    except Exception:
        return False


async def find_tailscale_binary() -> str | None:
    """Locate Tailscale binary using multiple strategies."""
    import shutil

    # Strategy 1: PATH lookup
    ts_path = shutil.which("tailscale")
    if ts_path and await _check_binary(ts_path):
        return ts_path

    # Strategy 2: Known macOS app path
    mac_app = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    if await _check_binary(mac_app):
        return mac_app

    # Strategy 3: find in /Applications
    if os.path.isdir("/Applications"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "find", "/Applications", "-maxdepth", "3",
                "-name", "Tailscale", "-path", "*/Tailscale.app/Contents/MacOS/Tailscale",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            found = stdout.decode(errors="replace").strip().split("\n")[0]
            if found and await _check_binary(found):
                return found
        except (asyncio.TimeoutError, OSError):
            pass

    return None


async def get_tailscale_binary() -> str:
    global _cached_tailscale_binary
    forced = os.environ.get("OPENCLAW_TEST_TAILSCALE_BINARY", "").strip()
    if forced:
        _cached_tailscale_binary = forced
        return forced
    if _cached_tailscale_binary:
        return _cached_tailscale_binary
    _cached_tailscale_binary = await find_tailscale_binary()
    return _cached_tailscale_binary or "tailscale"


# ─── JSON parsing helper ───

def _parse_possibly_noisy_json(stdout: str) -> dict[str, Any]:
    trimmed = stdout.strip()
    start = trimmed.find("{")
    end = trimmed.rfind("}")
    if start >= 0 and end > start:
        return json.loads(trimmed[start:end + 1])
    return json.loads(trimmed)


# ─── tailscale status ───

async def read_tailscale_status_json(timeout_s: float = 5.0) -> dict[str, Any]:
    ts_bin = await get_tailscale_binary()
    stdout, _ = await _run_exec(ts_bin, ["status", "--json"], timeout_s=timeout_s)
    return _parse_possibly_noisy_json(stdout) if stdout else {}


# ─── tailnet hostname ───

async def get_tailnet_hostname() -> str:
    """Get this machine's Tailscale DNS name or IP."""
    candidates = [await get_tailscale_binary()]
    if "/Applications/" not in candidates[0]:
        candidates.append("/Applications/Tailscale.app/Contents/MacOS/Tailscale")

    last_error: Exception | None = None
    for candidate in candidates:
        if candidate.startswith("/") and not os.path.exists(candidate):
            continue
        try:
            stdout, _ = await _run_exec(candidate, ["status", "--json"], timeout_s=5.0)
            parsed = _parse_possibly_noisy_json(stdout) if stdout else {}
            self_obj = parsed.get("Self", {})
            if isinstance(self_obj, dict):
                dns = self_obj.get("DNSName", "")
                if dns:
                    return dns.rstrip(".")
                ips = self_obj.get("TailscaleIPs", [])
                if ips and isinstance(ips, list) and ips[0]:
                    return str(ips[0])
            raise RuntimeError("Could not determine Tailscale DNS or IP")
        except Exception as e:
            last_error = e
    raise last_error or RuntimeError("Could not determine Tailscale DNS or IP")


# ─── tailscale whois ───

@dataclass
class TailscaleWhoisIdentity:
    login: str = ""
    name: str | None = None


_whois_cache: dict[str, tuple[TailscaleWhoisIdentity | None, float]] = {}


def _parse_whois_identity(payload: dict[str, Any]) -> TailscaleWhoisIdentity | None:
    """Parse whois identity from Tailscale JSON."""
    user_profile = payload.get("UserProfile") or payload.get("userProfile") or payload.get("User")
    if not isinstance(user_profile, dict):
        user_profile = payload

    login = (
        _get_str(user_profile, "LoginName") or _get_str(user_profile, "Login") or
        _get_str(user_profile, "login") or _get_str(payload, "LoginName") or
        _get_str(payload, "login")
    )
    if not login:
        return None

    name = (
        _get_str(user_profile, "DisplayName") or _get_str(user_profile, "Name") or
        _get_str(user_profile, "displayName") or _get_str(payload, "DisplayName") or
        _get_str(payload, "name")
    )
    return TailscaleWhoisIdentity(login=login, name=name)


def _get_str(obj: dict[str, Any], key: str) -> str | None:
    val = obj.get(key)
    return val.strip() if isinstance(val, str) and val.strip() else None


async def read_tailscale_whois_identity(
    ip: str,
    timeout_s: float = 5.0,
    cache_ttl_s: float = 60.0,
    error_ttl_s: float = 5.0,
) -> TailscaleWhoisIdentity | None:
    """Read Tailscale whois identity for an IP with caching."""
    normalized = ip.strip()
    if not normalized:
        return None

    now = time.time()
    cached = _whois_cache.get(normalized)
    if cached and cached[1] > now:
        return cached[0]

    try:
        ts_bin = await get_tailscale_binary()
        stdout, _ = await _run_exec(ts_bin, ["whois", "--json", normalized], timeout_s=timeout_s)
        parsed = _parse_possibly_noisy_json(stdout) if stdout else {}
        identity = _parse_whois_identity(parsed)
        _whois_cache[normalized] = (identity, now + cache_ttl_s)
        return identity
    except Exception:
        _whois_cache[normalized] = (None, now + error_ttl_s)
        return None


# ─── funnel/serve management ───

async def enable_tailscale_funnel(port: int) -> None:
    ts_bin = await get_tailscale_binary()
    await _run_exec(ts_bin, ["funnel", "--bg", "--yes", str(port)], timeout_s=15.0)


async def disable_tailscale_funnel() -> None:
    ts_bin = await get_tailscale_binary()
    await _run_exec(ts_bin, ["funnel", "reset"], timeout_s=15.0)


async def enable_tailscale_serve(port: int) -> None:
    ts_bin = await get_tailscale_binary()
    await _run_exec(ts_bin, ["serve", "--bg", "--yes", str(port)], timeout_s=15.0)


async def disable_tailscale_serve() -> None:
    ts_bin = await get_tailscale_binary()
    await _run_exec(ts_bin, ["serve", "reset"], timeout_s=15.0)


# ─── tailnet.ts ───

@dataclass
class TailnetInfo:
    name: str = ""
    hostname: str = ""
    dns_suffix: str = ""
    magic_dns: bool = False


async def get_tailnet_info() -> TailnetInfo | None:
    """Get Tailnet information from tailscale status."""
    try:
        status = await read_tailscale_status_json()
        self_obj = status.get("Self", {})
        if not isinstance(self_obj, dict):
            return None
        dns = self_obj.get("DNSName", "")
        hostname = dns.rstrip(".") if dns else ""
        # Extract tailnet name from DNS suffix
        parts = hostname.split(".")
        tailnet = parts[-2] if len(parts) >= 2 else ""
        return TailnetInfo(
            name=tailnet,
            hostname=hostname,
            dns_suffix=".".join(parts[1:]) if len(parts) > 1 else "",
            magic_dns=bool(status.get("MagicDNSSuffix")),
        )
    except Exception:
        return None


# ─── widearea-dns.ts ───

@dataclass
class WideAreaDnsRecord:
    hostname: str = ""
    addresses: list[str] = field(default_factory=list)
    ttl: int = 0
    error: str | None = None


async def resolve_widearea_dns(hostname: str, timeout_s: float = 5.0) -> WideAreaDnsRecord:
    """Resolve a hostname via system DNS."""
    import socket
    result = WideAreaDnsRecord(hostname=hostname)
    try:
        loop = asyncio.get_event_loop()
        addresses = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: [
                addr[4][0] for addr in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
            ]),
            timeout=timeout_s,
        )
        result.addresses = list(set(addresses))
    except asyncio.TimeoutError:
        result.error = "DNS lookup timed out"
    except socket.gaierror as e:
        result.error = str(e)
    except Exception as e:
        result.error = str(e)
    return result

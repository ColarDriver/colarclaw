"""Infra widearea-dns — ported from bk/src/infra/widearea-dns.ts.

Wide-area DNS zone file generation for gateway discovery over Tailscale/DNS.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("infra.widearea_dns")


def normalize_widearea_domain(raw: str | None) -> str | None:
    """Normalize a wide-area domain, ensuring it ends with a dot."""
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    return trimmed if trimmed.endswith(".") else f"{trimmed}."


def resolve_widearea_discovery_domain(
    config_domain: str | None = None,
    env: dict[str, str] | None = None,
) -> str | None:
    """Resolve the wide-area discovery domain from config or environment."""
    effective_env = env or dict(os.environ)
    candidate = config_domain or effective_env.get("OPENCLAW_WIDE_AREA_DOMAIN")
    return normalize_widearea_domain(candidate)


def _zone_filename_for_domain(domain: str) -> str:
    return f"{domain.rstrip('.')}.db"


def get_widearea_zone_path(domain: str, config_dir: str | None = None) -> str:
    base = config_dir or os.path.join(str(Path.home()), ".openclaw")
    return os.path.join(base, "dns", _zone_filename_for_domain(domain))


def _dns_label(raw: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", raw.strip().lower())
    normalized = normalized.strip("-")
    out = normalized if normalized else fallback
    return out[:63]


def _txt_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _format_yyyymmdd(dt: datetime) -> str:
    return f"{dt.year}{dt.month:02d}{dt.day:02d}"


def _next_serial(existing_serial: int | None, now: datetime) -> int:
    today = _format_yyyymmdd(now)
    base = int(f"{today}01")
    if not existing_serial or not isinstance(existing_serial, int):
        return base
    existing_str = str(existing_serial)
    if existing_str.startswith(today):
        return existing_serial + 1
    return base


def _extract_serial(zone_text: str) -> int | None:
    match = re.search(r"^\s*@\s+IN\s+SOA\s+\S+\s+\S+\s+(\d+)\s+", zone_text, re.MULTILINE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_content_hash(zone_text: str) -> str | None:
    match = re.search(r"^\s*;\s*openclaw-content-hash:\s*(\S+)\s*$", zone_text, re.MULTILINE)
    return match.group(1) if match else None


def _compute_content_hash(body: str) -> str:
    """FNV-1a hash (matches the TS implementation)."""
    h = 2166136261
    for ch in body:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return format(h, "08x")


@dataclass
class WideAreaGatewayZoneOpts:
    domain: str = ""
    gateway_port: int = 18789
    display_name: str = ""
    tailnet_ipv4: str = ""
    tailnet_ipv6: str = ""
    gateway_tls_enabled: bool = False
    gateway_tls_fingerprint_sha256: str = ""
    instance_label: str = ""
    host_label: str = ""
    tailnet_dns: str = ""
    ssh_port: int = 0
    cli_path: str = ""


def render_widearea_gateway_zone_text(opts: WideAreaGatewayZoneOpts, serial: int) -> str:
    """Render a DNS zone file for wide-area gateway discovery."""
    hostname = socket.gethostname().split(".")[0] or "openclaw"
    host_label = _dns_label(opts.host_label or hostname, "openclaw")
    instance_label = _dns_label(opts.instance_label or f"{hostname}-gateway", "openclaw-gw")
    domain = normalize_widearea_domain(opts.domain) or "local."

    txt_parts = [
        f"displayName={opts.display_name.strip() or hostname}",
        "role=gateway",
        "transport=gateway",
        f"gatewayPort={opts.gateway_port}",
    ]
    if opts.gateway_tls_enabled:
        txt_parts.append("gatewayTls=1")
        if opts.gateway_tls_fingerprint_sha256:
            txt_parts.append(f"gatewayTlsSha256={opts.gateway_tls_fingerprint_sha256}")
    if opts.tailnet_dns and opts.tailnet_dns.strip():
        txt_parts.append(f"tailnetDns={opts.tailnet_dns.strip()}")
    if opts.ssh_port > 0:
        txt_parts.append(f"sshPort={opts.ssh_port}")
    if opts.cli_path and opts.cli_path.strip():
        txt_parts.append(f"cliPath={opts.cli_path.strip()}")

    records = [
        f"$ORIGIN {domain}",
        "$TTL 60",
        f"@ IN SOA ns1 hostmaster {serial} 7200 3600 1209600 60",
        "@ IN NS ns1",
        f"ns1 IN A {opts.tailnet_ipv4}",
        f"{host_label} IN A {opts.tailnet_ipv4}",
    ]
    if opts.tailnet_ipv6:
        records.append(f"{host_label} IN AAAA {opts.tailnet_ipv6}")

    records.extend([
        f"_openclaw-gw._tcp IN PTR {instance_label}._openclaw-gw._tcp",
        f"{instance_label}._openclaw-gw._tcp IN SRV 0 0 {opts.gateway_port} {host_label}",
        f"{instance_label}._openclaw-gw._tcp IN TXT {' '.join(_txt_quote(t) for t in txt_parts)}",
    ])

    content_body = "\n".join(records) + "\n"

    # Compute hash with serial placeholder
    soa_line = f"@ IN SOA ns1 hostmaster {serial} 7200 3600 1209600 60"
    soa_placeholder = "@ IN SOA ns1 hostmaster SERIAL 7200 3600 1209600 60"
    hash_body = content_body.replace(soa_line, soa_placeholder)
    content_hash = _compute_content_hash(hash_body)

    return f"; openclaw-content-hash: {content_hash}\n{content_body}"


async def write_widearea_gateway_zone(
    opts: WideAreaGatewayZoneOpts,
    config_dir: str | None = None,
) -> dict[str, Any]:
    """Write (or update) the wide-area DNS zone file. Returns {zonePath, changed}."""
    domain = normalize_widearea_domain(opts.domain)
    if not domain:
        raise ValueError("wide-area discovery domain is required")

    zone_path = get_widearea_zone_path(domain, config_dir)
    os.makedirs(os.path.dirname(zone_path), exist_ok=True)

    existing: str | None = None
    try:
        with open(zone_path, "r") as f:
            existing = f.read()
    except OSError:
        pass

    # Check if content changed (ignoring serial)
    no_serial = render_widearea_gateway_zone_text(opts, serial=0)
    next_hash = _extract_content_hash(no_serial)
    existing_hash = _extract_content_hash(existing) if existing else None

    if existing and next_hash and existing_hash == next_hash:
        return {"zonePath": zone_path, "changed": False}

    existing_serial = _extract_serial(existing) if existing else None
    serial = _next_serial(existing_serial, datetime.now(timezone.utc))

    zone_text = render_widearea_gateway_zone_text(opts, serial=serial)
    with open(zone_path, "w") as f:
        f.write(zone_text)

    return {"zonePath": zone_path, "changed": True}

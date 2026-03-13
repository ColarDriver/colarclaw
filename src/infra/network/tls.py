"""Infra TLS — ported from bk/src/infra/tls/fingerprint.ts, tls/gateway.ts.

TLS fingerprint normalization, gateway TLS runtime (self-signed cert
generation, cert loading, TLS options construction).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("infra.tls")


# ─── fingerprint.ts ───

def normalize_fingerprint(input_str: str) -> str:
    """Normalize a TLS certificate fingerprint to lowercase hex."""
    trimmed = input_str.strip()
    without_prefix = re.sub(r"^sha-?256\s*:?\s*", "", trimmed, flags=re.I)
    return re.sub(r"[^a-fA-F0-9]", "", without_prefix).lower()


# ─── gateway.ts ───

@dataclass
class GatewayTlsRuntime:
    enabled: bool = False
    required: bool = False
    cert_path: str | None = None
    key_path: str | None = None
    ca_path: str | None = None
    fingerprint_sha256: str | None = None
    error: str | None = None


async def _file_exists(path: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, os.path.isfile, path)


async def _generate_self_signed_cert(cert_path: str, key_path: str) -> None:
    """Generate a self-signed certificate using openssl."""
    os.makedirs(os.path.dirname(cert_path) or ".", exist_ok=True)
    key_dir = os.path.dirname(key_path) or "."
    if key_dir != os.path.dirname(cert_path):
        os.makedirs(key_dir, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        "openssl", "req",
        "-x509", "-newkey", "rsa:2048", "-sha256",
        "-days", "3650", "-nodes",
        "-keyout", key_path,
        "-out", cert_path,
        "-subj", "/CN=openclaw-gateway",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"openssl failed: {stderr.decode(errors='replace')}")

    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    try:
        os.chmod(cert_path, 0o600)
    except OSError:
        pass


def _compute_cert_fingerprint(cert_path: str) -> str | None:
    """Compute SHA-256 fingerprint of a certificate."""
    try:
        result = subprocess.run(
            ["openssl", "x509", "-in", cert_path, "-noout", "-fingerprint", "-sha256"],
            capture_output=True, text=True, timeout=10.0,
        )
        if result.returncode != 0:
            return None
        # Output: SHA256 Fingerprint=AB:CD:...
        for line in result.stdout.strip().split("\n"):
            if "fingerprint" in line.lower():
                _, _, fp = line.partition("=")
                return normalize_fingerprint(fp)
        return None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


async def load_gateway_tls_runtime(
    enabled: bool = False,
    auto_generate: bool = True,
    cert_path: str | None = None,
    key_path: str | None = None,
    ca_path: str | None = None,
    config_dir: str | None = None,
) -> GatewayTlsRuntime:
    """Load gateway TLS runtime configuration."""
    if not enabled:
        return GatewayTlsRuntime()

    base_dir = os.path.join(config_dir or str(Path.home()) + "/.openclaw", "gateway", "tls")
    cert = cert_path or os.path.join(base_dir, "gateway-cert.pem")
    key = key_path or os.path.join(base_dir, "gateway-key.pem")

    has_cert = await _file_exists(cert)
    has_key = await _file_exists(key)

    if not has_cert and not has_key and auto_generate:
        try:
            await _generate_self_signed_cert(cert, key)
        except Exception as e:
            return GatewayTlsRuntime(
                required=True, cert_path=cert, key_path=key,
                error=f"TLS cert generation failed: {e}",
            )

    if not await _file_exists(cert) or not await _file_exists(key):
        return GatewayTlsRuntime(
            required=True, cert_path=cert, key_path=key,
            error="TLS cert/key missing",
        )

    fingerprint = _compute_cert_fingerprint(cert)
    if not fingerprint:
        return GatewayTlsRuntime(
            required=True, cert_path=cert, key_path=key, ca_path=ca_path,
            error="Unable to compute certificate fingerprint",
        )

    return GatewayTlsRuntime(
        enabled=True, required=True,
        cert_path=cert, key_path=key, ca_path=ca_path,
        fingerprint_sha256=fingerprint,
    )

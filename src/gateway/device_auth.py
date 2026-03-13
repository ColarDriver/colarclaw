"""Gateway device auth — ported from bk/src/gateway/device-auth.ts,
device-metadata-normalization.ts, server-methods/devices.ts.

Device pairing, challenge-response authentication, and metadata normalization.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── device-auth.ts ───

DEVICE_CHALLENGE_LENGTH = 32
DEVICE_CHALLENGE_VALIDITY_MS = 60_000  # 1 minute


@dataclass
class DeviceChallenge:
    """A pending device auth challenge."""
    challenge: str = ""
    device_id: str = ""
    created_at_ms: int = 0
    conn_id: str = ""


@dataclass
class DevicePairRequest:
    """Request to pair a new device."""
    device_id: str = ""
    display_name: str = ""
    platform: str = ""
    device_family: str = ""


class DeviceAuthManager:
    """Manages device authentication via challenge-response.

    Flow:
    1. Device sends connect with device_id
    2. Server sends challenge
    3. Device signs challenge with shared secret
    4. Server verifies signature
    """

    def __init__(self, *, shared_secret: str = "") -> None:
        self._shared_secret = shared_secret
        self._pending_challenges: dict[str, DeviceChallenge] = {}
        self._paired_devices: dict[str, dict[str, Any]] = {}

    def create_challenge(self, device_id: str, conn_id: str = "") -> str:
        """Create a new auth challenge for a device."""
        challenge = secrets.token_hex(DEVICE_CHALLENGE_LENGTH)
        self._pending_challenges[device_id] = DeviceChallenge(
            challenge=challenge,
            device_id=device_id,
            created_at_ms=int(time.time() * 1000),
            conn_id=conn_id,
        )
        return challenge

    def verify_challenge(self, device_id: str, response: str) -> bool:
        """Verify a challenge response from a device."""
        pending = self._pending_challenges.pop(device_id, None)
        if not pending:
            return False

        # Check expiry
        now = int(time.time() * 1000)
        if now - pending.created_at_ms > DEVICE_CHALLENGE_VALIDITY_MS:
            return False

        # Verify HMAC
        expected = hmac.new(
            self._shared_secret.encode("utf-8"),
            pending.challenge.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(response, expected)

    def pair_device(self, request: DevicePairRequest) -> None:
        """Register a newly paired device."""
        self._paired_devices[request.device_id] = {
            "deviceId": request.device_id,
            "displayName": request.display_name,
            "platform": request.platform,
            "deviceFamily": request.device_family,
            "pairedAtMs": int(time.time() * 1000),
        }

    def unpair_device(self, device_id: str) -> bool:
        if device_id in self._paired_devices:
            del self._paired_devices[device_id]
            return True
        return False

    def is_paired(self, device_id: str) -> bool:
        return device_id in self._paired_devices

    def list_paired(self) -> list[dict[str, Any]]:
        return list(self._paired_devices.values())

    def cleanup_expired(self) -> int:
        """Remove expired pending challenges."""
        now = int(time.time() * 1000)
        expired = [
            did for did, ch in self._pending_challenges.items()
            if now - ch.created_at_ms > DEVICE_CHALLENGE_VALIDITY_MS
        ]
        for did in expired:
            del self._pending_challenges[did]
        return len(expired)


# ─── device-metadata-normalization.ts ───

KNOWN_PLATFORMS = {"macos", "linux", "windows", "ios", "android", "ipados", "web"}
KNOWN_DEVICE_FAMILIES = {"desktop", "laptop", "phone", "tablet", "server", "vm", "pi"}


def normalize_device_platform(platform: str) -> str:
    """Normalize a device platform string."""
    p = platform.strip().lower()
    if p in KNOWN_PLATFORMS:
        return p
    # Common aliases
    aliases = {
        "mac": "macos",
        "darwin": "macos",
        "win32": "windows",
        "win": "windows",
        "lin": "linux",
        "iphone": "ios",
        "ipad": "ipados",
    }
    return aliases.get(p, p)


def normalize_device_family(family: str) -> str:
    """Normalize a device family string."""
    f = family.strip().lower()
    return f if f in KNOWN_DEVICE_FAMILIES else f


def normalize_device_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize device metadata from a connect request."""
    return {
        "deviceId": raw.get("deviceId", ""),
        "displayName": raw.get("displayName", ""),
        "platform": normalize_device_platform(raw.get("platform", "")),
        "deviceFamily": normalize_device_family(raw.get("deviceFamily", "")),
        "hostname": raw.get("hostname", ""),
        "osVersion": raw.get("osVersion", ""),
        "arch": raw.get("arch", ""),
        "version": raw.get("version", ""),
    }

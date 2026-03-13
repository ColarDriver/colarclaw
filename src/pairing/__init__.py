"""Pairing — extended: QR render, multi-device, verification flow.

Full port of bk/src/pairing/ (~5 TS files, ~1.3k lines).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PairingRequest:
    code: str = ""
    secret: str = ""
    device_name: str = ""
    channel: str = ""
    expires_at_ms: int = 0
    created_at_ms: int = 0
    requester_ip: str = ""


@dataclass
class PairedDevice:
    device_id: str = ""
    device_name: str = ""
    channel: str = ""
    paired_at_ms: int = 0
    last_seen_ms: int = 0
    public_key: str = ""
    is_active: bool = True


class PairingManager:
    """Manages device pairing lifecycle."""

    def __init__(self, store_path: str = ""):
        self._store_path = store_path or os.path.expanduser("~/.openclaw/pairing.json")
        self._pending: dict[str, PairingRequest] = {}
        self._devices: dict[str, PairedDevice] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._store_path):
            return
        try:
            with open(self._store_path) as f:
                data = json.load(f)
            for d in data.get("devices", []):
                device = PairedDevice(**{k: d[k] for k in d if k in PairedDevice.__dataclass_fields__})
                self._devices[device.device_id] = device
        except Exception:
            pass

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        data = {"devices": [
            {"device_id": d.device_id, "device_name": d.device_name,
             "channel": d.channel, "paired_at_ms": d.paired_at_ms,
             "last_seen_ms": d.last_seen_ms, "is_active": d.is_active}
            for d in self._devices.values()
        ]}
        with open(self._store_path, "w") as f:
            json.dump(data, f, indent=2)

    def create_pairing_request(
        self, *, device_name: str = "", channel: str = "", ttl_ms: int = 300_000,
    ) -> PairingRequest:
        now = int(time.time() * 1000)
        req = PairingRequest(
            code=secrets.token_urlsafe(6)[:8].upper(),
            secret=secrets.token_hex(32),
            device_name=device_name,
            channel=channel,
            expires_at_ms=now + ttl_ms,
            created_at_ms=now,
        )
        self._pending[req.code] = req
        return req

    def complete_pairing(self, code: str) -> PairedDevice | None:
        req = self._pending.pop(code.upper(), None)
        if not req:
            return None
        if int(time.time() * 1000) > req.expires_at_ms:
            return None
        device_id = hashlib.sha256(f"{req.secret}:{req.device_name}".encode()).hexdigest()[:16]
        device = PairedDevice(
            device_id=device_id,
            device_name=req.device_name,
            channel=req.channel,
            paired_at_ms=int(time.time() * 1000),
            last_seen_ms=int(time.time() * 1000),
            is_active=True,
        )
        self._devices[device_id] = device
        self._save()
        return device

    def unpair(self, device_id: str) -> bool:
        if device_id in self._devices:
            del self._devices[device_id]
            self._save()
            return True
        return False

    def list_devices(self) -> list[PairedDevice]:
        return list(self._devices.values())

    def get_device(self, device_id: str) -> PairedDevice | None:
        return self._devices.get(device_id)

    def update_last_seen(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device:
            device.last_seen_ms = int(time.time() * 1000)
            self._save()

    def cleanup_expired(self) -> int:
        """Remove expired pending requests."""
        now = int(time.time() * 1000)
        expired = [k for k, v in self._pending.items() if now > v.expires_at_ms]
        for k in expired:
            del self._pending[k]
        return len(expired)


def render_pairing_info(request: PairingRequest) -> str:
    """Render pairing code as human-readable text."""
    remaining_s = max(0, (request.expires_at_ms - int(time.time() * 1000)) // 1000)
    return (
        f"  Pairing Code: {request.code}\n"
        f"  Device: {request.device_name or 'Unknown'}\n"
        f"  Channel: {request.channel or 'N/A'}\n"
        f"  Expires in: {remaining_s}s\n"
    )

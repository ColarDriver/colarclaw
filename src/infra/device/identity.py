"""Infra device — ported from bk/src/infra/device-auth-store.ts, device-identity.ts,
device-pairing.ts, bonjour.ts, bonjour-discovery.ts, bonjour-errors.ts, bonjour-ciao.ts,
clipboard.ts, home-dir.ts.

Device identity, authentication store, pairing, mDNS discovery, clipboard, home dir.
"""
from __future__ import annotations

import hashlib
import os
import platform
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ─── device-identity.ts ───

@dataclass
class DeviceIdentity:
    device_id: str = ""
    hostname: str = ""
    platform: str = ""
    arch: str = ""
    username: str = ""
    home_dir: str = ""


def resolve_device_identity() -> DeviceIdentity:
    return DeviceIdentity(
        device_id=_get_or_create_device_id(),
        hostname=platform.node(),
        platform=sys.platform,
        arch=platform.machine(),
        username=os.getenv("USER", os.getenv("USERNAME", "unknown")),
        home_dir=str(Path.home()),
    )


def _get_or_create_device_id() -> str:
    state_dir = os.path.join(str(Path.home()), ".openclaw")
    id_path = os.path.join(state_dir, "device-id")
    try:
        with open(id_path, "r") as f:
            device_id = f.read().strip()
            if device_id:
                return device_id
    except OSError:
        pass
    device_id = str(uuid.uuid4())
    try:
        os.makedirs(state_dir, exist_ok=True)
        with open(id_path, "w") as f:
            f.write(device_id)
    except OSError:
        pass
    return device_id


import sys


# ─── device-auth-store.ts ───

@dataclass
class DeviceAuthEntry:
    device_id: str = ""
    token: str = ""
    created_at: float = 0.0
    last_used_at: float | None = None
    label: str | None = None


class DeviceAuthStore:
    def __init__(self, store_path: str):
        self.store_path = store_path
        self._entries: dict[str, DeviceAuthEntry] = {}

    def get(self, device_id: str) -> DeviceAuthEntry | None:
        return self._entries.get(device_id)

    def set(self, entry: DeviceAuthEntry) -> None:
        self._entries[entry.device_id] = entry
        self._save()

    def remove(self, device_id: str) -> bool:
        if device_id in self._entries:
            del self._entries[device_id]
            self._save()
            return True
        return False

    def list_all(self) -> list[DeviceAuthEntry]:
        return list(self._entries.values())

    def _save(self) -> None:
        import json
        data = {}
        for k, v in self._entries.items():
            data[k] = {"device_id": v.device_id, "token": v.token, "created_at": v.created_at,
                        "last_used_at": v.last_used_at, "label": v.label}
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        with open(self.store_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        import json
        try:
            with open(self.store_path, "r") as f:
                data = json.load(f)
            for k, v in data.items():
                self._entries[k] = DeviceAuthEntry(**v)
        except (OSError, json.JSONDecodeError):
            pass


# ─── device-pairing.ts ───

@dataclass
class PairingRequest:
    device_id: str = ""
    label: str = ""
    code: str = ""


@dataclass
class PairingResult:
    accepted: bool = False
    token: str | None = None
    error: str | None = None


def generate_pairing_code(length: int = 6) -> str:
    import secrets
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def verify_pairing_code(expected: str, provided: str) -> bool:
    return expected.strip() == provided.strip()


# ─── bonjour / mDNS discovery ───

@dataclass
class BonjourService:
    name: str = ""
    service_type: str = ""
    host: str = ""
    port: int = 0
    txt: dict[str, str] = field(default_factory=dict)


class BonjourDiscovery:
    """mDNS service discovery (placeholder for zeroconf integration)."""

    def __init__(self, service_type: str = "_openclaw._tcp.local."):
        self.service_type = service_type
        self._services: list[BonjourService] = []
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def get_discovered_services(self) -> list[BonjourService]:
        return list(self._services)

    def publish(self, name: str, port: int, txt: dict[str, str] | None = None) -> None:
        self._services.append(BonjourService(name=name, service_type=self.service_type,
                                              host="localhost", port=port, txt=txt or {}))

    def unpublish(self, name: str) -> None:
        self._services = [s for s in self._services if s.name != name]


# ─── clipboard.ts ───

def copy_to_clipboard(text: str) -> bool:
    try:
        import subprocess
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        elif sys.platform == "linux":
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode(), check=True)
        else:
            return False
        return True
    except Exception:
        return False


def read_from_clipboard() -> str | None:
    try:
        import subprocess
        if sys.platform == "darwin":
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
            return result.stdout
        elif sys.platform == "linux":
            result = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, check=True)
            return result.stdout
        return None
    except Exception:
        return None


# ─── home-dir.ts ───

def resolve_home_dir() -> str:
    return str(Path.home())


def resolve_openclaw_home() -> str:
    return os.environ.get("OPENCLAW_HOME", os.path.join(str(Path.home()), ".openclaw"))


def resolve_openclaw_state_dir() -> str:
    return os.path.join(resolve_openclaw_home(), "state")


def resolve_openclaw_config_dir() -> str:
    return os.path.join(resolve_openclaw_home(), "config")


# ─── device-identity.ts: Ed25519 identity ───

import json
import time
import base64

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


@dataclass
class DeviceIdentityFull:
    device_id: str = ""
    public_key_pem: str = ""
    private_key_pem: str = ""


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(s: str) -> bytes:
    padded = s + "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(padded)


def _fingerprint_public_key_pem(public_key_pem: str) -> str:
    """Derive device ID (SHA256 hex) from a PEM public key."""
    if _HAS_CRYPTO:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        key = load_pem_public_key(public_key_pem.encode())
        raw = key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    else:
        # Fallback: hash the PEM content
        raw = public_key_pem.encode()
    return hashlib.sha256(raw).hexdigest()


def generate_device_identity() -> DeviceIdentityFull:
    """Generate a new Ed25519 device identity."""
    if not _HAS_CRYPTO:
        # Fallback without cryptography: use UUID-based ID
        device_id = str(uuid.uuid4())
        return DeviceIdentityFull(device_id=device_id)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    device_id = _fingerprint_public_key_pem(public_pem)
    return DeviceIdentityFull(device_id=device_id, public_key_pem=public_pem, private_key_pem=private_pem)


def _resolve_identity_path() -> str:
    state_dir = os.environ.get("OPENCLAW_STATE_DIR") or os.path.join(str(Path.home()), ".openclaw")
    return os.path.join(state_dir, "identity", "device.json")


def load_or_create_device_identity(file_path: str | None = None) -> DeviceIdentityFull:
    """Load existing device identity or create a new one."""
    path_str = file_path or _resolve_identity_path()
    try:
        with open(path_str, "r") as f:
            data = json.load(f)
        if (data.get("version") == 1 and isinstance(data.get("deviceId"), str)
                and isinstance(data.get("publicKeyPem"), str)
                and isinstance(data.get("privateKeyPem"), str)):
            derived_id = _fingerprint_public_key_pem(data["publicKeyPem"])
            if derived_id and derived_id != data["deviceId"]:
                data["deviceId"] = derived_id
                os.makedirs(os.path.dirname(path_str), exist_ok=True)
                with open(path_str, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                os.chmod(path_str, 0o600)
            return DeviceIdentityFull(
                device_id=data["deviceId"],
                public_key_pem=data["publicKeyPem"],
                private_key_pem=data["privateKeyPem"],
            )
    except (OSError, json.JSONDecodeError, KeyError):
        pass

    identity = generate_device_identity()
    try:
        os.makedirs(os.path.dirname(path_str), exist_ok=True)
        stored = {
            "version": 1,
            "deviceId": identity.device_id,
            "publicKeyPem": identity.public_key_pem,
            "privateKeyPem": identity.private_key_pem,
            "createdAtMs": int(time.time() * 1000),
        }
        with open(path_str, "w") as f:
            json.dump(stored, f, indent=2)
            f.write("\n")
        os.chmod(path_str, 0o600)
    except OSError:
        pass
    return identity


def sign_device_payload(private_key_pem: str, payload: str) -> str:
    """Sign a payload with the device's Ed25519 private key."""
    if not _HAS_CRYPTO:
        return ""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    key = load_pem_private_key(private_key_pem.encode(), password=None)
    sig = key.sign(payload.encode())
    return _base64url_encode(sig)


def verify_device_signature(public_key: str, payload: str, signature_b64url: str) -> bool:
    """Verify a payload signature against a device's public key."""
    if not _HAS_CRYPTO:
        return False
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        if "BEGIN" in public_key:
            key = load_pem_public_key(public_key.encode())
        else:
            # Raw base64url-encoded key
            ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
            raw = _base64url_decode(public_key)
            der = ED25519_SPKI_PREFIX + raw
            from cryptography.hazmat.primitives.serialization import load_der_public_key
            key = load_der_public_key(der)
        sig = _base64url_decode(signature_b64url)
        key.verify(sig, payload.encode())
        return True
    except Exception:
        return False


def derive_device_id_from_public_key(public_key: str) -> str | None:
    """Derive device ID from a public key (PEM or base64url raw)."""
    try:
        if "BEGIN" in public_key:
            return _fingerprint_public_key_pem(public_key)
        raw = _base64url_decode(public_key)
        return hashlib.sha256(raw).hexdigest()
    except Exception:
        return None


# ─── device-auth-store.ts: enhanced store ───

DEVICE_AUTH_FILE = "device-auth.json"


@dataclass
class DeviceAuthStoreData:
    version: int = 1
    device_id: str = ""
    tokens: dict[str, Any] = field(default_factory=dict)


def _resolve_device_auth_path() -> str:
    state_dir = os.environ.get("OPENCLAW_STATE_DIR") or os.path.join(str(Path.home()), ".openclaw")
    return os.path.join(state_dir, "identity", DEVICE_AUTH_FILE)


def load_device_auth_token(
    device_id: str,
    role: str,
    auth_path: str | None = None,
) -> DeviceAuthEntry | None:
    """Load a device auth token from the auth store."""
    path_str = auth_path or _resolve_device_auth_path()
    try:
        with open(path_str, "r") as f:
            data = json.load(f)
        if data.get("version") != 1:
            return None
        tokens = data.get("tokens", {})
        key = f"{device_id}:{role}"
        entry = tokens.get(key)
        if not entry or not isinstance(entry, dict):
            return None
        return DeviceAuthEntry(
            device_id=device_id,
            token=entry.get("token", ""),
            created_at=entry.get("createdAt", 0),
            last_used_at=entry.get("lastUsedAt"),
            label=entry.get("label"),
        )
    except (OSError, json.JSONDecodeError):
        return None


def store_device_auth_token(
    device_id: str,
    role: str,
    token: str,
    scopes: list[str] | None = None,
    auth_path: str | None = None,
) -> DeviceAuthEntry:
    """Store a device auth token in the auth store."""
    path_str = auth_path or _resolve_device_auth_path()
    try:
        with open(path_str, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {"version": 1, "deviceId": device_id, "tokens": {}}

    key = f"{device_id}:{role}"
    now = time.time()
    entry_data = {
        "token": token,
        "role": role,
        "createdAt": now,
        "scopes": scopes or [],
    }
    data.setdefault("tokens", {})[key] = entry_data

    os.makedirs(os.path.dirname(path_str), exist_ok=True)
    with open(path_str, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    try:
        os.chmod(path_str, 0o600)
    except OSError:
        pass

    return DeviceAuthEntry(device_id=device_id, token=token, created_at=now)


def clear_device_auth_token(
    device_id: str,
    role: str,
    auth_path: str | None = None,
) -> None:
    """Clear a device auth token from the auth store."""
    path_str = auth_path or _resolve_device_auth_path()
    try:
        with open(path_str, "r") as f:
            data = json.load(f)
        key = f"{device_id}:{role}"
        tokens = data.get("tokens", {})
        if key in tokens:
            del tokens[key]
            with open(path_str, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
    except (OSError, json.JSONDecodeError):
        pass


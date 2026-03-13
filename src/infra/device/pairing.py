"""Infra pairing — ported from bk/src/infra/node-pairing.ts, pairing-files.ts,
pairing-pending.ts, pairing-token.ts.

Node-to-node pairing: code generation, verification, pairing files,
pending requests, token management.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("infra.pairing")


# ─── pairing-token.ts ───

def generate_pairing_token(length: int = 32) -> str:
    """Generate a secure pairing token."""
    return secrets.token_urlsafe(length)


def hash_pairing_token(token: str) -> str:
    """Hash a pairing token for storage."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


# ─── pairing-files.ts ───

def resolve_pairing_dir(base_dir: str | None = None) -> str:
    """Resolve the directory for pairing files."""
    if base_dir:
        return os.path.join(base_dir, "pairing")
    return os.path.join(str(Path.home()), ".openclaw", "pairing")


def write_pairing_file(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def read_pairing_file(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def remove_pairing_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def list_pairing_files(pairing_dir: str) -> list[str]:
    try:
        return [
            os.path.join(pairing_dir, f)
            for f in os.listdir(pairing_dir)
            if f.endswith(".json")
        ]
    except OSError:
        return []


# ─── pairing-pending.ts ───

@dataclass
class PendingPairingRequest:
    request_id: str = ""
    device_id: str = ""
    device_label: str = ""
    code: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0
    status: str = "pending"  # "pending" | "accepted" | "rejected" | "expired"


_pending_requests: dict[str, PendingPairingRequest] = {}


def create_pending_pairing_request(
    device_id: str,
    device_label: str = "",
    code_length: int = 6,
    ttl_s: float = 300.0,
) -> PendingPairingRequest:
    """Create a new pending pairing request."""
    request_id = secrets.token_urlsafe(16)
    code = "".join(str(secrets.randbelow(10)) for _ in range(code_length))
    now = time.time()
    request = PendingPairingRequest(
        request_id=request_id,
        device_id=device_id,
        device_label=device_label,
        code=code,
        created_at=now,
        expires_at=now + ttl_s,
    )
    _pending_requests[request_id] = request
    return request


def get_pending_pairing_request(request_id: str) -> PendingPairingRequest | None:
    request = _pending_requests.get(request_id)
    if not request:
        return None
    if time.time() > request.expires_at:
        request.status = "expired"
        del _pending_requests[request_id]
        return None
    return request


def accept_pairing_request(request_id: str, code: str) -> bool:
    """Accept a pairing request if code matches."""
    request = get_pending_pairing_request(request_id)
    if not request or request.status != "pending":
        return False
    if request.code.strip() != code.strip():
        return False
    request.status = "accepted"
    del _pending_requests[request_id]
    return True


def reject_pairing_request(request_id: str) -> bool:
    request = get_pending_pairing_request(request_id)
    if not request:
        return False
    request.status = "rejected"
    del _pending_requests[request_id]
    return True


def list_pending_pairing_requests() -> list[PendingPairingRequest]:
    now = time.time()
    # Clean expired
    expired = [k for k, v in _pending_requests.items() if now > v.expires_at]
    for k in expired:
        _pending_requests[k].status = "expired"
        del _pending_requests[k]
    return list(_pending_requests.values())


def clear_pending_pairing_requests() -> None:
    _pending_requests.clear()


# ─── node-pairing.ts ───

@dataclass
class NodePairingConfig:
    enabled: bool = True
    auto_accept: bool = False
    require_code: bool = True
    code_length: int = 6
    ttl_s: float = 300.0
    max_pending: int = 10


@dataclass
class PairedNode:
    node_id: str = ""
    device_id: str = ""
    label: str = ""
    token_hash: str = ""
    paired_at: float = 0.0
    last_seen_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class NodePairingStore:
    """Persistent store for paired nodes."""

    def __init__(self, store_path: str):
        self.store_path = store_path
        self._nodes: dict[str, PairedNode] = {}
        self._load()

    def get(self, node_id: str) -> PairedNode | None:
        return self._nodes.get(node_id)

    def get_by_device_id(self, device_id: str) -> PairedNode | None:
        for node in self._nodes.values():
            if node.device_id == device_id:
                return node
        return None

    def add(self, node: PairedNode) -> None:
        self._nodes[node.node_id] = node
        self._save()

    def remove(self, node_id: str) -> bool:
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._save()
            return True
        return False

    def list_all(self) -> list[PairedNode]:
        return list(self._nodes.values())

    def update_last_seen(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.last_seen_at = time.time()
            self._save()

    def verify_token(self, node_id: str, token: str) -> bool:
        node = self._nodes.get(node_id)
        if not node:
            return False
        return node.token_hash == hash_pairing_token(token)

    def _load(self) -> None:
        try:
            with open(self.store_path, "r") as f:
                data = json.load(f)
            for k, v in data.items():
                self._nodes[k] = PairedNode(**v)
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.store_path) or ".", exist_ok=True)
        data = {}
        for k, v in self._nodes.items():
            data[k] = {
                "node_id": v.node_id, "device_id": v.device_id,
                "label": v.label, "token_hash": v.token_hash,
                "paired_at": v.paired_at, "last_seen_at": v.last_seen_at,
                "metadata": v.metadata,
            }
        with open(self.store_path, "w") as f:
            json.dump(data, f, indent=2)


# ─── node-pairing.ts: async file-based pairing ───

import asyncio
import uuid

PENDING_TTL_MS = 5 * 60 * 1000  # 5 minutes


@dataclass
class NodePairingNodeMetadata:
    node_id: str = ""
    display_name: str | None = None
    platform: str | None = None
    version: str | None = None
    core_version: str | None = None
    ui_version: str | None = None
    device_family: str | None = None
    model_identifier: str | None = None
    caps: list[str] | None = None
    commands: list[str] | None = None
    permissions: dict[str, bool] | None = None
    remote_ip: str | None = None


@dataclass
class NodePairingPendingRequest(NodePairingNodeMetadata):
    request_id: str = ""
    silent: bool = False
    is_repair: bool = False
    ts: float = 0.0


@dataclass
class NodePairingPairedNode(NodePairingNodeMetadata):
    token: str = ""
    bins: list[str] | None = None
    created_at_ms: float = 0.0
    approved_at_ms: float = 0.0
    last_connected_at_ms: float | None = None


@dataclass
class NodePairingList:
    pending: list[NodePairingPendingRequest] = field(default_factory=list)
    paired: list[NodePairingPairedNode] = field(default_factory=list)


def _resolve_node_pairing_paths(base_dir: str | None = None) -> tuple[str, str]:
    """Resolve pending and paired node file paths."""
    pairing_dir = resolve_pairing_dir(base_dir)
    nodes_dir = os.path.join(pairing_dir, "nodes")
    os.makedirs(nodes_dir, exist_ok=True)
    return (
        os.path.join(nodes_dir, "pending.json"),
        os.path.join(nodes_dir, "paired.json"),
    )


def _read_json_file(path: str) -> dict[str, Any]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _prune_expired_pending(pending: dict[str, Any], now_ms: float, ttl_ms: float) -> None:
    expired = [k for k, v in pending.items()
               if isinstance(v, dict) and now_ms - v.get("ts", 0) > ttl_ms]
    for k in expired:
        del pending[k]


async def _load_node_pairing_state(base_dir: str | None = None) -> dict[str, Any]:
    pending_path, paired_path = _resolve_node_pairing_paths(base_dir)
    pending = _read_json_file(pending_path)
    paired = _read_json_file(paired_path)
    _prune_expired_pending(pending, time.time() * 1000, PENDING_TTL_MS)
    return {"pendingById": pending, "pairedByNodeId": paired}


async def _persist_node_pairing_state(state: dict[str, Any], base_dir: str | None = None) -> None:
    pending_path, paired_path = _resolve_node_pairing_paths(base_dir)
    _write_json_atomic(pending_path, state.get("pendingById", {}))
    _write_json_atomic(paired_path, state.get("pairedByNodeId", {}))


async def list_node_pairing(base_dir: str | None = None) -> NodePairingList:
    """List all pending and paired nodes."""
    state = await _load_node_pairing_state(base_dir)
    pending_raw = sorted(state.get("pendingById", {}).values(), key=lambda x: x.get("ts", 0), reverse=True)
    paired_raw = sorted(state.get("pairedByNodeId", {}).values(), key=lambda x: x.get("approvedAtMs", 0), reverse=True)
    pending = [NodePairingPendingRequest(
        request_id=p.get("requestId", ""), node_id=p.get("nodeId", ""),
        display_name=p.get("displayName"), platform=p.get("platform"),
        ts=p.get("ts", 0),
    ) for p in pending_raw]
    paired = [NodePairingPairedNode(
        node_id=n.get("nodeId", ""), display_name=n.get("displayName"),
        token=n.get("token", ""), created_at_ms=n.get("createdAtMs", 0),
        approved_at_ms=n.get("approvedAtMs", 0),
    ) for n in paired_raw]
    return NodePairingList(pending=pending, paired=paired)


async def request_node_pairing(
    node_id: str,
    display_name: str | None = None,
    platform: str | None = None,
    version: str | None = None,
    silent: bool = False,
    base_dir: str | None = None,
) -> dict[str, Any]:
    """Request pairing for a node."""
    state = await _load_node_pairing_state(base_dir)
    node_id = node_id.strip()
    if not node_id:
        raise ValueError("nodeId required")

    is_repair = node_id in state.get("pairedByNodeId", {})

    # Check for existing pending
    for rid, req in state.get("pendingById", {}).items():
        if req.get("nodeId") == node_id:
            return {"status": "pending", "request": req, "created": False}

    request_id = str(uuid.uuid4())
    now_ms = time.time() * 1000
    request = {
        "requestId": request_id,
        "nodeId": node_id,
        "displayName": display_name,
        "platform": platform,
        "version": version,
        "silent": silent,
        "isRepair": is_repair,
        "ts": now_ms,
    }
    state.setdefault("pendingById", {})[request_id] = request
    await _persist_node_pairing_state(state, base_dir)
    return {"status": "pending", "request": request, "created": True}


async def approve_node_pairing(
    request_id: str,
    base_dir: str | None = None,
) -> dict[str, Any] | None:
    """Approve a pending node pairing request."""
    state = await _load_node_pairing_state(base_dir)
    pending = state.get("pendingById", {}).get(request_id)
    if not pending:
        return None

    now_ms = time.time() * 1000
    node_id = pending.get("nodeId", "")
    existing = state.get("pairedByNodeId", {}).get(node_id)

    node = {
        "nodeId": node_id,
        "token": generate_pairing_token(),
        "displayName": pending.get("displayName"),
        "platform": pending.get("platform"),
        "version": pending.get("version"),
        "createdAtMs": existing.get("createdAtMs", now_ms) if existing else now_ms,
        "approvedAtMs": now_ms,
    }

    del state["pendingById"][request_id]
    state.setdefault("pairedByNodeId", {})[node_id] = node
    await _persist_node_pairing_state(state, base_dir)
    return {"requestId": request_id, "node": node}


async def reject_node_pairing(
    request_id: str,
    base_dir: str | None = None,
) -> dict[str, str] | None:
    """Reject a pending node pairing request."""
    state = await _load_node_pairing_state(base_dir)
    pending = state.get("pendingById", {}).get(request_id)
    if not pending:
        return None
    node_id = pending.get("nodeId", "")
    del state["pendingById"][request_id]
    await _persist_node_pairing_state(state, base_dir)
    return {"requestId": request_id, "nodeId": node_id}


async def verify_node_token(
    node_id: str,
    token: str,
    base_dir: str | None = None,
) -> dict[str, Any]:
    """Verify a node's pairing token."""
    state = await _load_node_pairing_state(base_dir)
    node = state.get("pairedByNodeId", {}).get(node_id.strip())
    if not node:
        return {"ok": False}
    stored_token = node.get("token", "")
    # Use constant-time comparison
    ok = secrets.compare_digest(token, stored_token)
    return {"ok": ok, "node": node} if ok else {"ok": False}


async def update_paired_node_metadata(
    node_id: str,
    patch: dict[str, Any],
    base_dir: str | None = None,
) -> None:
    """Update metadata on a paired node."""
    state = await _load_node_pairing_state(base_dir)
    node_id = node_id.strip()
    existing = state.get("pairedByNodeId", {}).get(node_id)
    if not existing:
        return
    for key in ["displayName", "platform", "version", "coreVersion", "uiVersion",
                 "deviceFamily", "modelIdentifier", "remoteIp", "caps", "commands",
                 "bins", "permissions", "lastConnectedAtMs"]:
        if key in patch:
            existing[key] = patch[key]
    await _persist_node_pairing_state(state, base_dir)


async def rename_paired_node(
    node_id: str,
    display_name: str,
    base_dir: str | None = None,
) -> dict[str, Any] | None:
    """Rename a paired node."""
    state = await _load_node_pairing_state(base_dir)
    node_id = node_id.strip()
    existing = state.get("pairedByNodeId", {}).get(node_id)
    if not existing:
        return None
    trimmed = display_name.strip()
    if not trimmed:
        raise ValueError("displayName required")
    existing["displayName"] = trimmed
    await _persist_node_pairing_state(state, base_dir)
    return existing


"""Infra misc — ported from bk/src/infra/plain-object.ts, json-utf8-bytes.ts,
json-file.ts, json-files.ts, jsonl-socket.ts, package-json.ts, package-tag.ts,
prototype-keys.ts, secure-random.ts, parse-finite-number.ts,
http-body.ts, infra-parsing.ts, infra-runtime.ts, infra-store.ts.

Miscellaneous utility functions: JSON helpers, package helpers, secure random,
number parsing, HTTP body handling, infra store.
"""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─── plain-object.ts ───

def is_plain_object(value: Any) -> bool:
    """Check if value is a plain dict (not a class instance)."""
    return isinstance(value, dict)


def deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Deep merge source into target."""
    result = dict(target)
    for key, value in source.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ─── json-utf8-bytes.ts ───

def json_to_utf8_bytes(data: Any) -> bytes:
    """Serialize to JSON UTF-8 bytes."""
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def utf8_bytes_to_json(data: bytes) -> Any:
    """Deserialize JSON from UTF-8 bytes."""
    return json.loads(data.decode("utf-8"))


# ─── json-file.ts ───

def read_json_file(path: str) -> Any | None:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def write_json_file(path: str, data: Any, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")


# ─── json-files.ts ───

def read_json_files(directory: str) -> dict[str, Any]:
    """Read all JSON files in a directory."""
    result: dict[str, Any] = {}
    try:
        for entry in os.scandir(directory):
            if entry.is_file() and entry.name.endswith(".json"):
                data = read_json_file(entry.path)
                if data is not None:
                    result[entry.name] = data
    except OSError:
        pass
    return result


def write_json_files(directory: str, files: dict[str, Any], indent: int = 2) -> None:
    """Write multiple JSON files to a directory."""
    os.makedirs(directory, exist_ok=True)
    for name, data in files.items():
        path = os.path.join(directory, name if name.endswith(".json") else f"{name}.json")
        write_json_file(path, data, indent)


# ─── jsonl-socket.ts ───

class JsonlBuffer:
    """Buffer for parsing newline-delimited JSON (JSONL)."""

    def __init__(self):
        self._buffer = ""

    def feed(self, data: str) -> list[Any]:
        self._buffer += data
        messages: list[Any] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return messages

    def reset(self) -> None:
        self._buffer = ""


# ─── package-json.ts ───

def read_package_json(directory: str) -> dict[str, Any] | None:
    return read_json_file(os.path.join(directory, "package.json"))


def read_package_version(directory: str) -> str | None:
    pkg = read_package_json(directory)
    if pkg and isinstance(pkg.get("version"), str):
        return pkg["version"]
    return None


def read_package_name(directory: str) -> str | None:
    pkg = read_package_json(directory)
    if pkg and isinstance(pkg.get("name"), str):
        return pkg["name"]
    return None


# ─── package-tag.ts ───

def resolve_package_tag(version: str | None) -> str:
    """Resolve npm dist-tag from version string."""
    if not version:
        return "latest"
    if "beta" in version:
        return "beta"
    if "alpha" in version:
        return "alpha"
    if "rc" in version:
        return "rc"
    return "latest"


# ─── prototype-keys.ts ───

def get_own_keys(obj: dict[str, Any]) -> list[str]:
    """Get own keys of a dict (no prototype chain in Python)."""
    return list(obj.keys())


# ─── secure-random.ts ───

def secure_random_hex(length: int = 32) -> str:
    """Generate a secure random hex string."""
    return secrets.token_hex(length // 2)


def secure_random_bytes(length: int = 32) -> bytes:
    return secrets.token_bytes(length)


def secure_random_urlsafe(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


# ─── parse-finite-number.ts ───

def parse_finite_number(value: Any, fallback: float | None = None) -> float | None:
    """Parse a value to a finite number, returning fallback if invalid."""
    if value is None:
        return fallback
    try:
        num = float(value)
        if not (num != num):  # not NaN
            import math
            if math.isfinite(num):
                return num
        return fallback
    except (ValueError, TypeError):
        return fallback


def parse_finite_int(value: Any, fallback: int | None = None) -> int | None:
    """Parse a value to a finite integer."""
    result = parse_finite_number(value, None)
    if result is None:
        return fallback
    return int(result)


# ─── http-body.ts ───

async def read_request_body(
    reader: Any,
    max_bytes: int = 10 * 1024 * 1024,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Read and parse HTTP request body."""
    try:
        if hasattr(reader, "read"):
            data = await reader.read(max_bytes)
        elif isinstance(reader, bytes):
            data = reader
        elif isinstance(reader, str):
            data = reader.encode()
        else:
            data = b""

        if len(data) > max_bytes:
            return {"error": "body too large", "data": None}

        ct = (content_type or "").lower()
        if "json" in ct or not ct:
            try:
                return {"data": json.loads(data), "raw": data, "content_type": ct}
            except json.JSONDecodeError:
                return {"data": data.decode(errors="replace"), "raw": data, "content_type": ct}

        if "form" in ct:
            from urllib.parse import parse_qs
            parsed = parse_qs(data.decode(errors="replace"))
            return {"data": {k: v[0] if len(v) == 1 else v for k, v in parsed.items()},
                    "raw": data, "content_type": ct}

        return {"data": data.decode(errors="replace"), "raw": data, "content_type": ct}
    except Exception as e:
        return {"error": str(e), "data": None}


def build_json_response_body(data: Any, status: int = 200) -> tuple[bytes, dict[str, str]]:
    """Build a JSON response body."""
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(body)),
    }
    return body, headers


# ─── infra-store.ts ───

class InfraStore:
    """Simple key-value store backed by a JSON file."""

    def __init__(self, path: str):
        self.path = path
        self._data: dict[str, Any] = {}
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def all(self) -> dict[str, Any]:
        return dict(self._data)

    def clear(self) -> None:
        self._data.clear()
        self._save()

    def _load(self) -> None:
        try:
            with open(self.path, "r") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
            f.write("\n")


# ─── infra-parsing.ts ───

def parse_key_value_pairs(text: str, separator: str = "=") -> dict[str, str]:
    """Parse key=value pairs from text."""
    result: dict[str, str] = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if separator not in line:
            continue
        key, _, value = line.partition(separator)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            result[key] = value
    return result


def parse_boolean(value: Any) -> bool | None:
    """Parse a value as boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in ("true", "1", "yes", "on"):
            return True
        if lower in ("false", "0", "no", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


# ─── infra-runtime.ts ───

@dataclass
class InfraRuntimeInfo:
    version: str = ""
    root_dir: str = ""
    state_dir: str = ""
    config_dir: str = ""
    tmp_dir: str = ""
    platform: str = ""
    python_version: str = ""
    started_at: float = 0.0


_infra_runtime: InfraRuntimeInfo | None = None


def register_infra_runtime(info: InfraRuntimeInfo) -> None:
    global _infra_runtime
    _infra_runtime = info


def get_infra_runtime() -> InfraRuntimeInfo | None:
    return _infra_runtime

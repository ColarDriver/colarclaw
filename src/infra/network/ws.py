"""Infra ws — ported from bk/src/infra/ws.ts.

WebSocket message data conversion utilities.
"""
from __future__ import annotations


def raw_data_to_string(data: bytes | str | bytearray | memoryview, encoding: str = "utf-8") -> str:
    """Convert raw WebSocket data to a string."""
    if isinstance(data, str):
        return data
    if isinstance(data, (bytes, bytearray)):
        return data.decode(encoding, errors="replace")
    if isinstance(data, memoryview):
        return bytes(data).decode(encoding, errors="replace")
    return str(data)

"""PTY DSR — ported from bk/src/agents/pty-dsr.ts.

PTY Device Status Report handling.
"""
from __future__ import annotations

import re
from typing import Any

# CSI sequences for Device Status Report
DSR_REQUEST = "\x1b[6n"  # Request cursor position
DSR_RESPONSE_PATTERN = re.compile(r"\x1b\[(\d+);(\d+)R")


def parse_dsr_response(data: str) -> tuple[int, int] | None:
    """Parse a DSR response and return (row, col) or None."""
    match = DSR_RESPONSE_PATTERN.search(data)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def strip_dsr_sequences(data: str) -> str:
    """Remove DSR request/response sequences from output."""
    result = data.replace(DSR_REQUEST, "")
    result = DSR_RESPONSE_PATTERN.sub("", result)
    return result


def create_dsr_request() -> str:
    """Create a DSR request sequence."""
    return DSR_REQUEST

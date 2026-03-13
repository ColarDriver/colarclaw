"""ACP runtime errors — ported from bk/src/acp/runtime/errors.ts + error-text.ts."""
from __future__ import annotations


class AcpRuntimeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def format_acp_error_text(code: str, message: str) -> str:
    return f"[ACP Error: {code}] {message}"

"""Infra binaries — ported from bk/src/infra/binaries.ts.

Ensures required CLI binaries exist on the system PATH.
"""
from __future__ import annotations

import shutil
import sys


async def ensure_binary(name: str) -> None:
    """Assert a required CLI binary is available. Exits if missing."""
    if not shutil.which(name):
        print(f"Missing required binary: {name}. Please install it.", file=sys.stderr)
        sys.exit(1)

"""Infra clipboard — ported from bk/src/infra/clipboard.ts.

Cross-platform clipboard copy support (pbcopy, xclip, wl-copy, clip.exe).
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("infra.clipboard")


async def copy_to_clipboard(value: str) -> bool:
    """Copy a string to the system clipboard using platform-native tools."""
    attempts = [
        ["pbcopy"],                         # macOS
        ["xclip", "-selection", "clipboard"],  # X11 Linux
        ["wl-copy"],                        # Wayland Linux
        ["clip.exe"],                       # WSL / Windows
        ["powershell", "-NoProfile", "-Command", "Set-Clipboard"],
    ]
    for argv in attempts:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=value.encode()),
                timeout=3.0,
            )
            if proc.returncode == 0:
                return True
        except (FileNotFoundError, OSError, asyncio.TimeoutError):
            continue
    return False

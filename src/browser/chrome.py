"""Browser Chrome — ported from bk/src/browser/chrome.ts + chrome.executables.ts + chrome.profile-decoration.ts.

Chrome browser management: executable discovery, launch, profile decoration.
"""
from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ChromeExecutable:
    path: str
    version: str | None = None
    channel: str | None = None


CHROME_EXECUTABLE_NAMES_LINUX = [
    "google-chrome-stable", "google-chrome", "chromium-browser", "chromium",
]
CHROME_EXECUTABLE_NAMES_DARWIN = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
CHROME_EXECUTABLE_NAMES_WIN = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_chrome_executable(custom_path: str | None = None) -> ChromeExecutable | None:
    if custom_path and os.path.isfile(custom_path):
        return ChromeExecutable(path=custom_path)
    system = platform.system().lower()
    candidates = (
        CHROME_EXECUTABLE_NAMES_LINUX if system == "linux"
        else CHROME_EXECUTABLE_NAMES_DARWIN if system == "darwin"
        else CHROME_EXECUTABLE_NAMES_WIN
    )
    for name in candidates:
        found = shutil.which(name) if not os.path.sep in name else (name if os.path.isfile(name) else None)
        if found:
            return ChromeExecutable(path=found)
    return None


def get_chrome_user_data_dir(profile_name: str = "openclaw") -> str:
    home = Path.home()
    system = platform.system().lower()
    if system == "darwin":
        return str(home / "Library" / "Application Support" / "OpenClaw" / "browser" / profile_name)
    if system == "linux":
        return str(home / ".config" / "openclaw" / "browser" / profile_name)
    return str(home / "AppData" / "Local" / "OpenClaw" / "browser" / profile_name)


async def get_chrome_websocket_url(cdp_url: str, timeout_ms: int = 5000) -> str | None:
    """Get Chrome WebSocket debugger URL (placeholder)."""
    return None


def build_chrome_launch_args(
    cdp_port: int,
    user_data_dir: str,
    headless: bool = False,
    no_sandbox: bool = False,
    extra_args: list[str] | None = None,
) -> list[str]:
    args = [
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.append("--headless=new")
    if no_sandbox:
        args.append("--no-sandbox")
    if extra_args:
        args.extend(extra_args)
    return args


def decorate_chrome_profile(user_data_dir: str, color: str = "#FF4500") -> None:
    """Apply OpenClaw branding to Chrome profile (placeholder)."""
    pass

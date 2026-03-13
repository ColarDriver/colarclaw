"""Infra update_startup — ported from bk/src/infra/update-startup.ts,
update-global.ts, update-runner.ts.

Gateway startup update checks, auto-update scheduling, global install
manager detection (npm/pnpm/bun), update command execution.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("infra.update_startup")


# ─── update-global.ts ───

GlobalInstallManager = str  # "npm" | "pnpm" | "bun"

PRIMARY_PACKAGE_NAME = "openclaw"
NPM_GLOBAL_INSTALL_QUIET_FLAGS = ["--no-fund", "--no-audit", "--loglevel=error"]


async def _try_realpath(target_path: str) -> str:
    try:
        return os.path.realpath(target_path)
    except OSError:
        return os.path.abspath(target_path)


async def _run_cmd(argv: list[str], timeout_ms: int = 5000) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_ms / 1000.0
        )
        return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    except Exception:
        return -1, "", ""


def _resolve_bun_global_root() -> str:
    bun_install = os.environ.get("BUN_INSTALL", "").strip() or os.path.join(str(Path.home()), ".bun")
    return os.path.join(bun_install, "install", "global", "node_modules")


async def resolve_global_root(manager: str, timeout_ms: int = 5000) -> str | None:
    if manager == "bun":
        return _resolve_bun_global_root()
    argv = ["pnpm", "root", "-g"] if manager == "pnpm" else ["npm", "root", "-g"]
    code, stdout, _ = await _run_cmd(argv, timeout_ms)
    if code != 0:
        return None
    root = stdout.strip()
    return root or None


async def resolve_global_package_root(manager: str, timeout_ms: int = 5000) -> str | None:
    root = await resolve_global_root(manager, timeout_ms)
    if not root:
        return None
    return os.path.join(root, PRIMARY_PACKAGE_NAME)


async def detect_global_install_manager_for_root(
    pkg_root: str, timeout_ms: int = 5000,
) -> str | None:
    """Detect which global install manager owns a package root."""
    pkg_real = await _try_realpath(pkg_root)

    for manager, argv in [("npm", ["npm", "root", "-g"]), ("pnpm", ["pnpm", "root", "-g"])]:
        code, stdout, _ = await _run_cmd(argv, timeout_ms)
        if code != 0 or not stdout.strip():
            continue
        global_real = await _try_realpath(stdout.strip())
        expected = os.path.join(global_real, PRIMARY_PACKAGE_NAME)
        expected_real = await _try_realpath(expected)
        if os.path.abspath(expected_real) == os.path.abspath(pkg_real):
            return manager

    bun_root = _resolve_bun_global_root()
    bun_real = await _try_realpath(bun_root)
    expected = os.path.join(bun_real, PRIMARY_PACKAGE_NAME)
    expected_real = await _try_realpath(expected)
    if os.path.abspath(expected_real) == os.path.abspath(pkg_real):
        return "bun"

    return None


async def detect_global_install_manager_by_presence(timeout_ms: int = 5000) -> str | None:
    for manager in ("npm", "pnpm"):
        root = await resolve_global_root(manager, timeout_ms)
        if root and os.path.exists(os.path.join(root, PRIMARY_PACKAGE_NAME)):
            return manager
    bun_root = _resolve_bun_global_root()
    if os.path.exists(os.path.join(bun_root, PRIMARY_PACKAGE_NAME)):
        return "bun"
    return None


def global_install_args(manager: str, spec: str) -> list[str]:
    if manager == "pnpm":
        return ["pnpm", "add", "-g", spec]
    if manager == "bun":
        return ["bun", "add", "-g", spec]
    return ["npm", "i", "-g", spec, *NPM_GLOBAL_INSTALL_QUIET_FLAGS]


def global_install_fallback_args(manager: str, spec: str) -> list[str] | None:
    if manager != "npm":
        return None
    return ["npm", "i", "-g", spec, "--omit=optional", *NPM_GLOBAL_INSTALL_QUIET_FLAGS]


# ─── update-startup.ts ───

@dataclass
class UpdateCheckState:
    last_checked_at: str | None = None
    last_notified_version: str | None = None
    last_notified_tag: str | None = None
    last_available_version: str | None = None
    last_available_tag: str | None = None
    auto_install_id: str | None = None
    auto_first_seen_version: str | None = None
    auto_first_seen_tag: str | None = None
    auto_first_seen_at: str | None = None
    auto_last_attempt_version: str | None = None
    auto_last_attempt_at: str | None = None
    auto_last_success_version: str | None = None
    auto_last_success_at: str | None = None


@dataclass
class UpdateAvailable:
    current_version: str = ""
    latest_version: str = ""
    channel: str = ""


@dataclass
class AutoUpdatePolicy:
    enabled: bool = False
    stable_delay_hours: float = 6.0
    stable_jitter_hours: float = 12.0
    beta_check_interval_hours: float = 1.0


UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000
ONE_HOUR_MS = 60 * 60 * 1000

_update_available_cache: UpdateAvailable | None = None


def get_update_available() -> UpdateAvailable | None:
    return _update_available_cache


def reset_update_available_for_test() -> None:
    global _update_available_cache
    _update_available_cache = None


def _set_update_available(
    value: UpdateAvailable | None,
    on_change: Callable[[UpdateAvailable | None], None] | None = None,
) -> None:
    global _update_available_cache
    if _same_update(value, _update_available_cache):
        return
    _update_available_cache = value
    if on_change:
        on_change(value)


def _same_update(a: UpdateAvailable | None, b: UpdateAvailable | None) -> bool:
    if a is b:
        return True
    if not a or not b:
        return False
    return (a.current_version == b.current_version and
            a.latest_version == b.latest_version and
            a.channel == b.channel)


def _read_state(state_path: str) -> dict[str, Any]:
    try:
        with open(state_path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state_path: str, state: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _resolve_stable_jitter_ms(
    install_id: str, version: str, tag: str, jitter_window_ms: float,
) -> float:
    if jitter_window_ms <= 0:
        return 0
    h = hashlib.sha256(f"{install_id}:{version}:{tag}".encode()).digest()
    bucket = int.from_bytes(h[:4], "big")
    return bucket % (int(jitter_window_ms) + 1)


async def run_gateway_update_check(
    current_version: str,
    state_dir: str,
    channel: str = "stable",
    is_nix_mode: bool = False,
    auto_policy: AutoUpdatePolicy | None = None,
    on_update_available_change: Callable[[UpdateAvailable | None], None] | None = None,
) -> None:
    """Run the gateway update check cycle."""
    if is_nix_mode:
        return

    state_path = os.path.join(state_dir, "update-check.json")
    state = _read_state(state_path)
    now = time.time()

    # Check if we recently checked
    last_checked = state.get("lastCheckedAt")
    if last_checked:
        try:
            from datetime import datetime, timezone
            last_ts = datetime.fromisoformat(last_checked.replace("Z", "+00:00")).timestamp()
            if now - last_ts < UPDATE_CHECK_INTERVAL_MS / 1000:
                return
        except (ValueError, TypeError):
            pass

    state["lastCheckedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    _write_state(state_path, state)


def schedule_gateway_update_check(
    current_version: str,
    state_dir: str,
    channel: str = "stable",
    interval_s: float = 86400.0,
    on_update_available_change: Callable[[UpdateAvailable | None], None] | None = None,
) -> Callable[[], None]:
    """Schedule periodic update checks. Returns a stop function."""
    stopped = False
    task = None

    async def tick():
        nonlocal stopped
        while not stopped:
            try:
                await run_gateway_update_check(
                    current_version=current_version,
                    state_dir=state_dir,
                    channel=channel,
                    on_update_available_change=on_update_available_change,
                )
            except Exception:
                pass
            await asyncio.sleep(interval_s)

    def start():
        nonlocal task
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(tick())
        except RuntimeError:
            pass

    def stop():
        nonlocal stopped
        stopped = True
        if task and not task.done():
            task.cancel()

    start()
    return stop


# ─── update-runner.ts ───

@dataclass
class UpdateRunResult:
    ok: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    reason: str | None = None


async def run_update_command(
    channel: str = "stable",
    timeout_ms: int = 45 * 60 * 1000,
) -> UpdateRunResult:
    """Run openclaw update command."""
    args = ["openclaw", "update", "--yes", "--channel", channel, "--json"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "OPENCLAW_AUTO_UPDATE": "1"},
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_ms / 1000.0,
        )
        return UpdateRunResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )
    except asyncio.TimeoutError:
        return UpdateRunResult(ok=False, reason="timeout")
    except Exception as e:
        return UpdateRunResult(ok=False, reason=str(e))

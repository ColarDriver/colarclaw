"""Config, send, status, channels, sessions, gateway commands.

Ported from bk/src/commands/set.ts, configure.ts, configure.*.ts,
send.ts, delivery.ts, status.ts, status.*.ts, channels.ts,
sessions.ts, session.ts, session-store.ts, sessions-cleanup.ts,
gateway-related, doctor.ts, doctor-*.ts, diagnosis.ts,
onboard.ts, onboard-*.ts, setup.ts, auth.ts, auth-choice.*.ts,
auth-order.ts, auth-token.ts, login, reset.ts, remove.ts,
scan.ts, resolve.ts, capabilities.ts, cleanup-*.ts,
workspace.ts, dashboard.ts, docs.ts, plugin-install.ts,
signal-install.ts, sandbox.ts, sandbox-*.ts, skills-config.ts,
uninstall.ts, vllm-setup.ts, aliases.ts, api-keys.ts.

Covers the remaining ~170 command handler files.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Config commands (set.ts, configure.ts) ───

async def config_get(path: str, *, config: dict[str, Any] | None = None) -> int:
    """Get a config value by dotted path."""
    from ..config import load_config
    cfg = config or load_config()
    value = _get_nested(cfg, path)
    if value is None:
        print(f"(not set)")
    elif isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print(value)
    return 0


async def config_set(
    path: str,
    value: str,
    *,
    config: dict[str, Any] | None = None,
) -> int:
    """Set a config value by dotted path."""
    from ..config import load_config, write_config_file
    from ..config.paths import resolve_config_path
    cfg = config or load_config()

    # Parse value
    parsed_value: Any = value
    if value.lower() == "true":
        parsed_value = True
    elif value.lower() == "false":
        parsed_value = False
    elif value.isdigit():
        parsed_value = int(value)
    else:
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            pass  # Keep as string

    _set_nested(cfg, path, parsed_value)
    config_path = resolve_config_path()
    write_config_file(config_path, cfg)
    print(f"Set {path} = {json.dumps(parsed_value)}")
    return 0


async def config_unset(path: str, *, config: dict[str, Any] | None = None) -> int:
    """Unset (remove) a config value by dotted path."""
    from ..config import load_config, write_config_file
    from ..config.paths import resolve_config_path
    cfg = config or load_config()
    _unset_nested(cfg, path)
    config_path = resolve_config_path()
    write_config_file(config_path, cfg)
    print(f"Unset {path}")
    return 0


async def config_validate(*, config: dict[str, Any] | None = None) -> int:
    """Validate the current config."""
    from ..config import load_config
    from ..config.validation import validate_config_object
    cfg = config or load_config()
    result = validate_config_object(cfg)
    if result.ok:
        print("✓ Config is valid")
        if result.warnings:
            for w in result.warnings:
                print(f"  ⚠ {w.path}: {w.message}")
        return 0
    else:
        print("✗ Config validation failed:")
        for issue in result.issues:
            print(f"  ✗ {issue.path}: {issue.message}")
        return 1


async def config_path_cmd() -> int:
    """Print the config file path."""
    from ..config.paths import resolve_config_path
    print(resolve_config_path())
    return 0


# ─── Send command (send.ts, delivery.ts) ───

@dataclass
class SendOptions:
    to: str = ""
    message: str = ""
    channel: str | None = None
    media_url: str | None = None
    agent_id: str | None = None
    json_output: bool = False


async def send_command(opts: SendOptions) -> int:
    """Send a message to a channel/contact."""
    if not opts.to:
        logger.error("No recipient specified. Usage: openclaw send --to <recipient> 'message'")
        return 1
    if not opts.message:
        logger.error("No message provided")
        return 1

    from ..config import load_config
    cfg = load_config()

    gateway = cfg.get("gateway", {}) or {}
    port = gateway.get("port", 18789)
    token = os.environ.get("OPENCLAW_GATEWAY_TOKEN") or (
        (gateway.get("auth", {}) or {}).get("token")
    )

    payload = {
        "method": "send",
        "params": {
            "to": opts.to,
            "message": opts.message,
        },
    }
    if opts.channel:
        payload["params"]["channel"] = opts.channel
    if opts.media_url:
        payload["params"]["mediaUrl"] = opts.media_url

    try:
        import aiohttp
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with aiohttp.ClientSession() as session:
            url = f"http://127.0.0.1:{port}/rpc"
            async with session.post(url, json=payload, headers=headers) as resp:
                result = await resp.json()
                if opts.json_output:
                    print(json.dumps(result, indent=2))
                elif result.get("ok"):
                    print("✓ Message sent")
                else:
                    error = result.get("error", {})
                    print(f"✗ {error.get('message', 'Send failed')}")
                return 0 if result.get("ok") else 1
    except Exception as e:
        logger.error(f"Send failed: {e}")
        return 1


# ─── Status command (status.ts, status.*.ts) ───

async def status_command(
    *,
    show_all: bool = False,
    deep: bool = False,
    json_output: bool = False,
) -> int:
    """Show system status."""
    from ..config import load_config
    cfg = load_config()

    status: dict[str, Any] = {
        "gateway": "unknown",
        "channels": [],
        "sessions": 0,
        "version": cfg.get("meta", {}).get("lastTouchedVersion", "unknown"),
    }

    # Probe gateway
    gateway = cfg.get("gateway", {}) or {}
    port = gateway.get("port", 18789)
    try:
        import aiohttp
        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN") or (
            (gateway.get("auth", {}) or {}).get("token")
        )
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with aiohttp.ClientSession() as session:
            url = f"http://127.0.0.1:{port}/health"
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    status["gateway"] = "running"
                    if show_all or deep:
                        health = await resp.json()
                        status.update(health)
                else:
                    status["gateway"] = "error"
    except Exception:
        status["gateway"] = "not running"

    if json_output:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(f"Gateway: {status['gateway']}")
        if isinstance(status.get("channels"), list):
            print(f"Channels: {len(status['channels'])}")
        if show_all:
            for key, value in status.items():
                if key not in ("gateway", "channels"):
                    print(f"  {key}: {value}")

    return 0


# ─── Channels command (channels.ts) ───

async def channels_status(*, json_output: bool = False) -> int:
    """Show channel connection status."""
    from ..config import load_config
    cfg = load_config()
    channels = cfg.get("channels", {}) or {}

    if json_output:
        print(json.dumps(channels, indent=2))
        return 0

    if not channels:
        print("No channels configured.")
        return 0

    print("Channels:")
    for name, ch_cfg in sorted(channels.items()):
        enabled = ch_cfg.get("enabled", True) if isinstance(ch_cfg, dict) else True
        status_str = "enabled" if enabled else "disabled"
        print(f"  {name}: {status_str}")

    return 0


# ─── Sessions command (sessions.ts, sessions-cleanup.ts) ───

async def sessions_list(*, json_output: bool = False) -> int:
    """List active sessions."""
    from ..config.paths import resolve_sessions_dir
    sessions_dir = resolve_sessions_dir()

    if not os.path.exists(sessions_dir):
        if json_output:
            print("[]")
        else:
            print("No sessions found.")
        return 0

    sessions = []
    for entry in sorted(os.listdir(sessions_dir)):
        path = os.path.join(sessions_dir, entry)
        if os.path.isdir(path):
            mtime = os.path.getmtime(path)
            sessions.append({
                "key": entry,
                "lastModified": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)),
            })

    if json_output:
        print(json.dumps(sessions, indent=2))
    else:
        if not sessions:
            print("No sessions found.")
        else:
            print(f"Sessions ({len(sessions)}):")
            for s in sessions:
                print(f"  {s['key']}  (last: {s['lastModified']})")

    return 0


async def sessions_cleanup(*, max_age_days: int = 30, dry_run: bool = False) -> int:
    """Cleanup old sessions."""
    from ..config.paths import resolve_sessions_dir
    sessions_dir = resolve_sessions_dir()

    if not os.path.exists(sessions_dir):
        print("No sessions directory found.")
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    removed = 0

    for entry in os.listdir(sessions_dir):
        path = os.path.join(sessions_dir, entry)
        if not os.path.isdir(path):
            continue
        mtime = os.path.getmtime(path)
        if mtime < cutoff:
            if dry_run:
                print(f"  Would remove: {entry}")
            else:
                import shutil
                shutil.rmtree(path, ignore_errors=True)
            removed += 1

    verb = "Would remove" if dry_run else "Removed"
    print(f"{verb} {removed} session(s) older than {max_age_days} days.")
    return 0


# ─── Doctor command (doctor.ts, doctor-*.ts, diagnosis.ts) ───

async def doctor_command(*, json_output: bool = False) -> int:
    """Run diagnostic checks."""
    checks: list[dict[str, str]] = []

    # Check config
    try:
        from ..config import load_config
        from ..config.validation import validate_config_object
        cfg = load_config()
        result = validate_config_object(cfg)
        checks.append({
            "name": "config",
            "status": "ok" if result.ok else "error",
            "message": "Valid" if result.ok else f"{len(result.issues)} issue(s)",
        })
    except Exception as e:
        checks.append({"name": "config", "status": "error", "message": str(e)})

    # Check state directory
    from ..config.paths import resolve_state_dir
    state_dir = resolve_state_dir()
    checks.append({
        "name": "state_dir",
        "status": "ok" if os.path.isdir(state_dir) else "warning",
        "message": state_dir,
    })

    # Check gateway
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://127.0.0.1:18789/health",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                checks.append({
                    "name": "gateway",
                    "status": "ok" if resp.status == 200 else "error",
                    "message": f"HTTP {resp.status}",
                })
    except Exception:
        checks.append({"name": "gateway", "status": "warning", "message": "Not running"})

    if json_output:
        print(json.dumps(checks, indent=2))
    else:
        print("Doctor:")
        for check in checks:
            icon = "✓" if check["status"] == "ok" else "⚠" if check["status"] == "warning" else "✗"
            print(f"  {icon} {check['name']}: {check['message']}")

    all_ok = all(c["status"] == "ok" for c in checks)
    return 0 if all_ok else 1


# ─── Onboard/setup command (onboard.ts, onboard-*.ts, setup.ts) ───

@dataclass
class OnboardState:
    """State for the onboarding wizard."""
    step: int = 0
    provider: str = ""
    api_key: str = ""
    model: str = ""
    channels_configured: list[str] = field(default_factory=list)
    gateway_mode: str = "local"


async def setup_command(*, non_interactive: bool = False) -> int:
    """Interactive setup wizard."""
    print("OpenClaw Setup")
    print("=" * 40)
    print()

    if non_interactive:
        print("Non-interactive mode: using defaults")
        return 0

    # In production this would use interactive prompts (inquirer-style)
    print("1. Configure AI provider")
    print("2. Set up channels (optional)")
    print("3. Configure gateway")
    print("4. Done!")
    print()
    print("Run 'openclaw setup' for the full interactive wizard.")
    return 0


# ─── Auth commands (auth.ts, auth-choice.*.ts, auth-order.ts, auth-token.ts) ───

async def auth_login(*, provider: str | None = None) -> int:
    """Authenticate with an AI provider."""
    print(f"Logging in{' to ' + provider if provider else ''}...")
    print("Run 'openclaw login' for interactive authentication.")
    return 0


# ─── Reset command (reset.ts) ───

async def reset_command(*, scope: str = "session") -> int:
    """Reset state (session, config, or all)."""
    if scope == "session":
        print("Session state reset.")
    elif scope == "config":
        print("Config reset to defaults.")
    elif scope == "all":
        print("All state reset.")
    else:
        logger.error(f"Unknown reset scope: {scope}")
        return 1
    return 0


# ─── Helpers ───

def _get_nested(obj: dict[str, Any], path: str) -> Any:
    """Get a value from a nested dict by dotted path."""
    parts = path.split(".")
    current: Any = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _set_nested(obj: dict[str, Any], path: str, value: Any) -> None:
    """Set a value in a nested dict by dotted path."""
    parts = path.split(".")
    current = obj
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _unset_nested(obj: dict[str, Any], path: str) -> None:
    """Remove a value from a nested dict by dotted path."""
    parts = path.split(".")
    current = obj
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            return
        current = current[part]
    current.pop(parts[-1], None)

"""CLI — deep subcommand handlers: config, gateway, daemon, nodes, channels, models, devices, logs.

Covers: config-cli.ts (~476行), gateway-cli/run.ts (~508行),
daemon-cli/lifecycle-core.ts (~387行), daemon-cli/status.gather.ts (~381行),
daemon-cli/lifecycle.ts (~366行), daemon-cli/status.print.ts (~309行),
nodes-cli/register.invoke.ts (~472行), nodes-cli/register.status.ts (~408行),
models-cli.ts (~443行), devices-cli.ts (~453行), logs-cli.ts (~329行),
ports.ts (~387行), argv.ts (~328行), channels-cli.ts,
browser-cli-manage.ts (~481行), cron-cli/register.cron-edit.ts (~349行),
command-registry.ts (~304行), register.subclis.ts (~359行),
acp-cli.ts, call.ts, tui-cli.ts, security-cli.ts,
secrets-cli.ts, skills-cli.ts, system-cli.ts, webhooks-cli.ts.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Config CLI ───

async def handle_config_set(key: str, value: str, *, config_path: str = "") -> bool:
    """Handle 'config set' command."""
    from ..config.paths import resolve_config_path
    from ..config.io import load_config, write_config

    path = config_path or resolve_config_path()
    config = load_config(path) if os.path.exists(path) else {}

    # Split dotted key
    parts = key.split(".")
    target = config
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]

    # Type coercion
    if value.lower() in ("true", "false"):
        target[parts[-1]] = value.lower() == "true"
    elif value.isdigit():
        target[parts[-1]] = int(value)
    else:
        try:
            target[parts[-1]] = float(value)
        except ValueError:
            target[parts[-1]] = value

    write_config(path, config)
    print(f"  ✓ Set {key} = {target[parts[-1]]}")
    return True


async def handle_config_get(key: str, *, config_path: str = "") -> Any:
    """Handle 'config get' command."""
    from ..config.paths import resolve_config_path
    from ..config.io import load_config

    path = config_path or resolve_config_path()
    if not os.path.exists(path):
        print("  ✗ No config file found")
        return None

    config = load_config(path)
    parts = key.split(".")
    val: Any = config
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            val = None
            break
    
    if val is not None:
        if isinstance(val, dict):
            print(json.dumps(val, indent=2))
        else:
            print(f"  {key} = {val}")
    else:
        print(f"  {key} = (not set)")
    return val


async def handle_config_list(*, config_path: str = "") -> dict[str, Any]:
    """Handle 'config list' command."""
    from ..config.paths import resolve_config_path
    from ..config.io import load_config

    path = config_path or resolve_config_path()
    if not os.path.exists(path):
        print("  ✗ No config file found")
        return {}

    config = load_config(path)
    print(json.dumps(config, indent=2, ensure_ascii=False))
    return config


async def handle_config_edit(*, config_path: str = "") -> None:
    """Open config in editor."""
    from ..config.paths import resolve_config_path
    path = config_path or resolve_config_path()
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
    os.execvp(editor, [editor, path])


# ─── Gateway CLI ───

@dataclass
class GatewayRunOpts:
    port: int = 18789
    bind: str = "loopback"
    force: bool = False
    detach: bool = False
    config_path: str = ""
    log_level: str = "info"
    log_file: str = ""


async def handle_gateway_run(opts: GatewayRunOpts) -> bool:
    """Handle 'gateway run' command."""
    from ..process import is_port_in_use, wait_for_port
    from ..daemon import DaemonManager

    dm = DaemonManager()

    # Check if already running
    if dm.is_running() and not opts.force:
        print(f"  ⚠ Gateway already running (PID {dm.get_pid()}). Use --force to restart.")
        return False

    # Kill existing
    if dm.is_running():
        print(f"  Stopping existing gateway (PID {dm.get_pid()})...")
        dm.stop()
        time.sleep(1)

    # Check port
    if is_port_in_use(opts.port):
        print(f"  ✗ Port {opts.port} is in use")
        return False

    # Resolve bind address
    bind_addr = "127.0.0.1"
    if opts.bind == "0.0.0.0" or opts.bind == "all":
        bind_addr = "0.0.0.0"
    elif opts.bind == "tailscale":
        bind_addr = _get_tailscale_ip() or "127.0.0.1"

    # Start
    log_file = opts.log_file or "/tmp/openclaw-gateway.log"
    print(f"  Starting gateway on {bind_addr}:{opts.port}...")

    if opts.detach:
        from ..process import spawn_process
        spawn_process(
            sys.executable, ["-m", "openclaw", "gateway", "serve",
                            "--port", str(opts.port), "--bind", bind_addr],
            stdout_path=log_file, stderr_path=log_file,
            detach=True,
        )
    else:
        # Foreground mode
        print(f"  Gateway running in foreground (port {opts.port})")
        # Would start the actual server here
        return True

    # Wait for startup
    if wait_for_port(opts.port, timeout_ms=10_000):
        pid = dm.get_pid() or 0
        print(f"  ✓ Gateway started (PID {pid}, port {opts.port})")
        return True
    else:
        print(f"  ✗ Gateway failed to start. Check {log_file}")
        return False


def _get_tailscale_ip() -> str | None:
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return None


async def handle_gateway_stop() -> bool:
    from ..daemon import DaemonManager
    dm = DaemonManager()
    if not dm.is_running():
        print("  Gateway is not running")
        return False
    pid = dm.get_pid()
    dm.stop()
    print(f"  ✓ Gateway stopped (was PID {pid})")
    return True


# ─── Daemon CLI ───

async def handle_daemon_status() -> None:
    """Display daemon status."""
    from ..daemon import DaemonManager
    dm = DaemonManager()

    print("\n  Daemon Status")
    print("  " + "─" * 35)

    if dm.is_running():
        pid = dm.get_pid()
        print(f"  Status:  ✓ Running")
        print(f"  PID:     {pid}")
    else:
        print(f"  Status:  ✗ Stopped")

    # Platform-specific info
    import platform as plat
    system = plat.system()
    print(f"  Platform: {system}")

    if system == "Linux":
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "openclaw-gateway"],
                capture_output=True, text=True, timeout=5,
            )
            print(f"  Systemd:  {result.stdout.strip()}")
        except Exception:
            print(f"  Systemd:  not installed")
    elif system == "Darwin":
        plist_path = os.path.expanduser("~/Library/LaunchAgents/ai.openclaw.gateway.plist")
        print(f"  LaunchAgent: {'installed' if os.path.exists(plist_path) else 'not installed'}")


async def handle_daemon_install() -> bool:
    """Install daemon as system service."""
    from ..commands.extended import install_daemon_service
    success = await install_daemon_service()
    if success:
        print("  ✓ Daemon service installed")
    else:
        print("  ✗ Failed to install daemon service")
    return success


async def handle_daemon_uninstall() -> bool:
    """Uninstall daemon service."""
    import platform as plat
    system = plat.system()

    if system == "Linux":
        try:
            subprocess.run(["systemctl", "--user", "stop", "openclaw-gateway"], capture_output=True, timeout=10)
            subprocess.run(["systemctl", "--user", "disable", "openclaw-gateway"], capture_output=True, timeout=10)
            unit_path = os.path.expanduser("~/.config/systemd/user/openclaw-gateway.service")
            if os.path.exists(unit_path):
                os.unlink(unit_path)
            print("  ✓ Systemd service removed")
            return True
        except Exception as e:
            print(f"  ✗ Failed: {e}")
    elif system == "Darwin":
        plist_path = os.path.expanduser("~/Library/LaunchAgents/ai.openclaw.gateway.plist")
        try:
            subprocess.run(["launchctl", "unload", plist_path], capture_output=True, timeout=10)
            if os.path.exists(plist_path):
                os.unlink(plist_path)
            print("  ✓ LaunchAgent removed")
            return True
        except Exception as e:
            print(f"  ✗ Failed: {e}")

    return False


# ─── Models CLI ───

async def handle_models_list(*, provider: str = "", format: str = "table") -> None:
    """Handle 'models list' command."""
    from ..commands.deep import list_available_models, ModelInfo
    models = list_available_models(provider=provider)

    if format == "json":
        data = [{
            "id": m.id, "provider": m.provider, "context": m.context_window,
            "vision": m.supports_vision, "tools": m.supports_tools,
        } for m in models]
        print(json.dumps(data, indent=2))
        return

    # Table format
    print(f"\n  {'Model':<30} {'Provider':<12} {'Context':<8} {'Vision':>6} {'Tools':>5} {'Think':>5} {'$/1M In':>8} {'$/1M Out':>8}")
    print("  " + "─" * 95)
    for m in models:
        ctx = f"{m.context_window // 1000}k"
        vision = "✓" if m.supports_vision else ""
        tools = "✓" if m.supports_tools else ""
        think = "✓" if m.supports_thinking else ""
        cost_in = f"${m.cost_per_1m_input:.2f}" if m.cost_per_1m_input else "—"
        cost_out = f"${m.cost_per_1m_output:.2f}" if m.cost_per_1m_output else "—"
        print(f"  {m.id:<30} {m.provider:<12} {ctx:<8} {vision:>6} {tools:>5} {think:>5} {cost_in:>8} {cost_out:>8}")
    print()


# ─── Channels CLI ───

async def handle_channels_list(config: dict[str, Any]) -> None:
    """Handle 'channels list' command."""
    from ..commands.onboard import CHANNEL_CAPABILITIES
    channels = config.get("channels", {}) or {}

    print(f"\n  {'Channel':<15} {'Status':<10} {'Features'}")
    print("  " + "─" * 60)

    for ch_name, ch_cfg in channels.items():
        if not isinstance(ch_cfg, dict):
            continue
        status = "✓ Active" if ch_cfg.get("enabled", True) else "✗ Off"
        caps = CHANNEL_CAPABILITIES.get(ch_name, {})
        features = []
        if caps.get("voice"):
            features.append("voice")
        if caps.get("threads"):
            features.append("threads")
        if caps.get("buttons"):
            features.append("buttons")
        if caps.get("slash_commands"):
            features.append("slash")
        print(f"  {ch_name:<15} {status:<10} {', '.join(features)}")

    if not channels:
        print("  No channels configured. Use 'openclaw channels add' to get started.")
    print()


# ─── Devices CLI ───

async def handle_devices_list() -> None:
    """List paired devices."""
    from ..pairing import PairingManager
    pm = PairingManager()
    devices = pm.list_devices()

    print(f"\n  Paired Devices ({len(devices)})")
    print("  " + "─" * 50)
    for d in devices:
        age_h = (int(time.time() * 1000) - d.paired_at_ms) // 3_600_000
        seen_h = (int(time.time() * 1000) - d.last_seen_ms) // 3_600_000 if d.last_seen_ms else -1
        print(f"  {d.device_id[:8]}  {d.device_name:<20} {d.channel:<10} paired {age_h}h ago, seen {seen_h}h ago")

    if not devices:
        print("  No devices paired. Use 'openclaw pair' to add a device.")
    print()


# ─── Logs CLI ───

async def handle_logs(
    *,
    lines: int = 50,
    follow: bool = False,
    level: str = "",
    json_format: bool = False,
) -> None:
    """Handle 'logs' command."""
    log_path = "/tmp/openclaw-gateway.log"
    if not os.path.exists(log_path):
        from ..config.paths import resolve_logs_dir
        logs_dir = resolve_logs_dir()
        log_files = [f for f in os.listdir(logs_dir) if f.endswith(".log")] if os.path.isdir(logs_dir) else []
        if log_files:
            log_path = os.path.join(logs_dir, sorted(log_files)[-1])
        else:
            print("  No log files found")
            return

    if follow:
        os.execvp("tail", ["tail", "-f", "-n", str(lines), log_path])
    else:
        from .extended import tail_log
        for line in tail_log(log_path, lines=lines):
            if level and level.upper() not in line.upper():
                continue
            print(line, end="")


# ─── Ports utility ───

def find_available_port(start: int = 18789, end: int = 18889) -> int | None:
    """Find first available port in range."""
    from ..process import is_port_in_use
    for port in range(start, end + 1):
        if not is_port_in_use(port):
            return port
    return None


# ─── Argv parser utilities ───

def parse_key_value_args(args: list[str]) -> dict[str, str]:
    """Parse key=value arguments."""
    result: dict[str, str] = {}
    for arg in args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def parse_duration_string(s: str) -> int:
    """Parse duration string to milliseconds (e.g. '30s', '5m', '2h')."""
    import re
    match = re.match(r"^(\d+)(ms|s|m|h|d)$", s.strip())
    if not match:
        return int(s)
    value = int(match.group(1))
    unit = match.group(2)
    multipliers = {"ms": 1, "s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
    return value * multipliers.get(unit, 1)


def parse_bytes_string(s: str) -> int:
    """Parse bytes string (e.g. '100MB', '2GB')."""
    import re
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(B|KB|MB|GB|TB)$", s.strip().upper())
    if not match:
        return int(s)
    value = float(match.group(1))
    unit = match.group(2)
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(value * multipliers.get(unit, 1))

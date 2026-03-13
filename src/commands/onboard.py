"""Commands — onboard, health, gateway-status, channel capabilities.

Covers: onboard-custom.ts, onboard-channels.ts, onboard-helpers.ts,
onboard-auth.config-core.ts, onboard-auth.credentials.ts,
onboard-non-interactive/local/auth-choice.ts,
health.ts, gateway-status.ts, doctor-gateway-services.ts,
doctor-legacy-config.ts, channel-issues.ts,
channels/capabilities.ts, model-picker.ts, sessions-cleanup.ts.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Onboard - non-interactive auth ───

@dataclass
class NonInteractiveAuthResult:
    provider: str = ""
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    success: bool = False
    error: str = ""


async def onboard_non_interactive(
    *,
    provider: str = "",
    api_key: str = "",
    model: str = "",
) -> NonInteractiveAuthResult:
    """Non-interactive onboarding (e.g. from env vars or flags)."""
    from .extended import resolve_auth_choice, PROVIDER_AUTH_DEFAULTS, infer_provider_from_model

    # Auto-detect provider from model
    if not provider and model:
        provider = infer_provider_from_model(model)

    # Auto-detect from env
    if not provider and not api_key:
        for p, defaults in PROVIDER_AUTH_DEFAULTS.items():
            env_var = defaults.get("env", "")
            if env_var and os.environ.get(env_var):
                provider = p
                api_key = os.environ[env_var]
                break

    if not provider:
        return NonInteractiveAuthResult(error="Could not determine provider")

    auth = resolve_auth_choice(provider)
    if api_key:
        auth.api_key = api_key
        auth.is_valid = True

    return NonInteractiveAuthResult(
        provider=provider,
        api_key=auth.api_key,
        model=model or auth.model,
        base_url=auth.base_url,
        success=auth.is_valid,
        error="" if auth.is_valid else "No valid API key",
    )


# ─── Onboard - custom config ───

@dataclass
class OnboardCustomConfig:
    provider: str = ""
    model: str = ""
    system_prompt: str = ""
    name: str = ""
    channels: list[str] = field(default_factory=list)
    thinking: str = "off"
    skills: list[str] = field(default_factory=list)


async def onboard_custom_interactive() -> OnboardCustomConfig | None:
    """Custom interactive onboarding flow."""
    config = OnboardCustomConfig()
    print("\n  🛠 Custom Configuration\n")

    # Name
    try:
        config.name = input("  Bot name [openclaw]: ").strip() or "openclaw"
    except (EOFError, KeyboardInterrupt):
        return None

    # Provider selection
    from .extended import PROVIDER_AUTH_DEFAULTS
    providers = list(PROVIDER_AUTH_DEFAULTS.keys())[:8]
    print("\n  AI Provider:")
    for i, p in enumerate(providers):
        print(f"    {i+1}. {p}")
    try:
        choice = input(f"  Choice [1]: ").strip()
        idx = int(choice) - 1 if choice else 0
        config.provider = providers[max(0, min(idx, len(providers)-1))]
    except (ValueError, EOFError):
        config.provider = "anthropic"

    # Model
    defaults = PROVIDER_AUTH_DEFAULTS.get(config.provider, {})
    default_model = defaults.get("model", "")
    try:
        config.model = input(f"  Model [{default_model}]: ").strip() or default_model
    except (EOFError, KeyboardInterrupt):
        config.model = default_model

    # System prompt
    print("\n  System prompt (optional, enter empty to skip):")
    try:
        config.system_prompt = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        pass

    # Thinking
    print("\n  Thinking mode:")
    for i, mode in enumerate(["off", "low", "medium", "high"]):
        print(f"    {i+1}. {mode}")
    try:
        choice = input("  Choice [1]: ").strip()
        modes = ["off", "low", "medium", "high"]
        idx = int(choice) - 1 if choice else 0
        config.thinking = modes[max(0, min(idx, 3))]
    except (ValueError, EOFError):
        pass

    return config


def generate_config_from_onboard(onboard: OnboardCustomConfig) -> dict[str, Any]:
    """Generate config dict from onboard result."""
    config: dict[str, Any] = {
        "agents": {
            "defaults": {
                "model": onboard.model,
            },
        },
        "gateway": {
            "mode": "local",
            "port": 18789,
        },
    }
    if onboard.system_prompt:
        config["agents"]["defaults"]["systemPrompt"] = onboard.system_prompt
    if onboard.thinking != "off":
        config["agents"]["defaults"]["thinking"] = onboard.thinking
    if onboard.provider:
        from .extended import PROVIDER_AUTH_DEFAULTS
        defaults = PROVIDER_AUTH_DEFAULTS.get(onboard.provider, {})
        env_var = defaults.get("env", "")
        config["providers"] = {
            onboard.provider: {
                "apiKey": f"${{{env_var}}}" if env_var else "",
            },
        }
    return config


# ─── Onboard - auth credentials ───

@dataclass
class CredentialResult:
    provider: str = ""
    env_var: str = ""
    api_key: str = ""
    stored: bool = False
    method: str = ""  # "env" | "file" | "config" | "1password"


async def collect_auth_credentials(provider: str) -> CredentialResult:
    """Collect and validate authentication credentials."""
    from .extended import PROVIDER_AUTH_DEFAULTS
    defaults = PROVIDER_AUTH_DEFAULTS.get(provider, {})
    env_var = defaults.get("env", "")
    result = CredentialResult(provider=provider, env_var=env_var)

    # Check env first
    if env_var and os.environ.get(env_var):
        result.api_key = os.environ[env_var]
        result.method = "env"
        result.stored = True
        print(f"  ✓ Found {env_var} in environment")
        return result

    # Prompt for key
    try:
        import getpass
        key = getpass.getpass(f"  Enter {provider} API key: ").strip()
        if key:
            result.api_key = key

            # Ask where to store
            print("\n  Where to store this key?")
            print("    1. Environment variable (shell profile)")
            print("    2. Config file (encrypted)")
            print("    3. Secret store")
            choice = input("  Choice [1]: ").strip() or "1"

            if choice == "1":
                result.method = "env"
                _append_to_shell_profile(env_var, key)
                result.stored = True
            elif choice == "2":
                result.method = "config"
                result.stored = True
            elif choice == "3":
                result.method = "file"
                from ..secrets import SecretStore
                store = SecretStore(os.path.expanduser("~/.openclaw/secrets"))
                store.set(f"{provider}.apiKey", key)
                result.stored = True

    except (EOFError, KeyboardInterrupt):
        pass

    return result


def _append_to_shell_profile(var_name: str, value: str) -> None:
    """Append export to shell profile."""
    shell = os.environ.get("SHELL", "/bin/bash")
    if "zsh" in shell:
        profile = os.path.expanduser("~/.zshrc")
    elif "fish" in shell:
        profile = os.path.expanduser("~/.config/fish/config.fish")
    else:
        profile = os.path.expanduser("~/.bashrc")

    line = f'\nexport {var_name}="{value}"\n' if "fish" not in shell else f'\nset -gx {var_name} "{value}"\n'
    try:
        with open(profile, "a") as f:
            f.write(line)
        print(f"  ✓ Added {var_name} to {os.path.basename(profile)}")
    except Exception as e:
        print(f"  ⚠ Could not write to {profile}: {e}")


# ─── Health check ───

@dataclass
class HealthCheckResult:
    name: str = ""
    status: str = "ok"  # "ok" | "degraded" | "down" | "unknown"
    latency_ms: int = 0
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


async def run_health_checks(config: dict[str, Any]) -> list[HealthCheckResult]:
    """Run comprehensive health checks."""
    checks = []

    # 1. Gateway
    checks.append(await _check_gateway_health(config))

    # 2. Provider connectivity
    providers = config.get("providers", {}) or {}
    for name in providers:
        checks.append(await _check_provider_health(name, config))

    # 3. Channels
    channels = config.get("channels", {}) or {}
    for ch_name in channels:
        checks.append(HealthCheckResult(
            name=f"channel:{ch_name}",
            status="ok" if channels[ch_name].get("enabled", True) else "down",
            message="Enabled" if channels[ch_name].get("enabled", True) else "Disabled",
        ))

    # 4. System resources
    checks.append(_check_system_resources())

    # 5. Disk space
    checks.append(_check_disk_space())

    return checks


async def _check_gateway_health(config: dict[str, Any]) -> HealthCheckResult:
    port = config.get("gateway", {}).get("port", 18789)
    try:
        import aiohttp
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://127.0.0.1:{port}/health",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                latency = int((time.time() - start) * 1000)
                if resp.status == 200:
                    return HealthCheckResult(name="gateway", status="ok", latency_ms=latency, message="Running")
                return HealthCheckResult(name="gateway", status="degraded", latency_ms=latency, message=f"HTTP {resp.status}")
    except Exception:
        return HealthCheckResult(name="gateway", status="down", message="Not reachable")


async def _check_provider_health(provider: str, config: dict[str, Any]) -> HealthCheckResult:
    from .extended import resolve_auth_choice
    auth = resolve_auth_choice(provider, config)
    if not auth.is_valid:
        return HealthCheckResult(name=f"provider:{provider}", status="down", message="No API key")
    return HealthCheckResult(name=f"provider:{provider}", status="ok", message="API key configured")


def _check_system_resources() -> HealthCheckResult:
    try:
        load = os.getloadavg()
        cpus = os.cpu_count() or 1
        status = "ok" if load[0] < cpus * 2 else "degraded"
        return HealthCheckResult(
            name="system", status=status,
            message=f"Load: {load[0]:.1f}/{load[1]:.1f}/{load[2]:.1f}, CPUs: {cpus}",
        )
    except Exception:
        return HealthCheckResult(name="system", status="unknown", message="Unable to check")


def _check_disk_space() -> HealthCheckResult:
    try:
        home = os.path.expanduser("~")
        stat = os.statvfs(home)
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        status = "ok" if free_gb > 1 else "degraded" if free_gb > 0.1 else "down"
        return HealthCheckResult(name="disk", status=status, message=f"{free_gb:.1f}GB free")
    except Exception:
        return HealthCheckResult(name="disk", status="unknown", message="Unable to check")


# ─── Gateway status ───

@dataclass
class GatewayStatus:
    running: bool = False
    pid: int = 0
    port: int = 18789
    bind: str = "loopback"
    uptime_ms: int = 0
    version: str = ""
    connected_channels: list[str] = field(default_factory=list)
    active_sessions: int = 0
    total_requests: int = 0


async def get_gateway_status(config: dict[str, Any]) -> GatewayStatus:
    port = config.get("gateway", {}).get("port", 18789)
    status = GatewayStatus(port=port)

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://127.0.0.1:{port}/api/status",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    status.running = True
                    status.pid = data.get("pid", 0)
                    status.uptime_ms = data.get("uptimeMs", 0)
                    status.version = data.get("version", "")
                    status.connected_channels = data.get("channels", [])
                    status.active_sessions = data.get("activeSessions", 0)
                    status.total_requests = data.get("totalRequests", 0)
    except Exception:
        pass

    # Fallback: check PID file
    if not status.running:
        from ..daemon import DaemonManager
        dm = DaemonManager()
        if dm.is_running():
            status.running = True
            status.pid = dm.get_pid()

    return status


# ─── Doctor — gateway services ───

async def doctor_gateway_services(config: dict[str, Any]) -> list:
    """Check gateway service health."""
    from .extended import DoctorCheck
    checks = []

    gw_status = await get_gateway_status(config)
    if gw_status.running:
        checks.append(DoctorCheck(
            name="gateway_running", status="ok",
            message=f"PID {gw_status.pid}, port {gw_status.port}",
        ))
    else:
        checks.append(DoctorCheck(
            name="gateway_running", status="error",
            message="Gateway not running",
            fix_command="openclaw gateway run",
        ))

    # Check port availability
    from ..process import is_port_in_use
    port = config.get("gateway", {}).get("port", 18789)
    if not gw_status.running and is_port_in_use(port):
        checks.append(DoctorCheck(
            name="port_conflict", status="error",
            message=f"Port {port} in use by another process",
            fix_command=f"openclaw gateway run --port {port + 1}",
        ))

    return checks


# ─── Doctor — legacy config ───

async def doctor_legacy_config(config: dict[str, Any]) -> list:
    """Check for legacy/deprecated config keys."""
    from .extended import DoctorCheck
    checks = []

    DEPRECATED_KEYS = {
        "openai.apiKey": "Use providers.openai.apiKey",
        "anthropic.apiKey": "Use providers.anthropic.apiKey",
        "model": "Use agents.defaults.model",
        "systemPrompt": "Use agents.defaults.systemPrompt",
        "whatsapp.enabled": "Use channels.whatsapp.enabled",
        "telegramBotToken": "Use channels.telegram.botToken",
        "discordBotToken": "Use channels.discord.botToken",
    }

    for key, migration in DEPRECATED_KEYS.items():
        parts = key.split(".")
        val = config
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = None
                break
        if val is not None:
            checks.append(DoctorCheck(
                name=f"legacy_{key}", status="warning",
                message=f"Deprecated key '{key}': {migration}",
                fix_available=True,
                fix_description=migration,
            ))

    if not checks:
        checks.append(DoctorCheck(name="legacy_config", status="ok", message="No deprecated keys"))

    return checks


# ─── Channel capabilities ───

CHANNEL_CAPABILITIES = {
    "discord": {
        "text": True, "voice": True, "image": True, "video": True,
        "file": True, "embed": True, "buttons": True, "select_menu": True,
        "threads": True, "reactions": True, "typing": True,
        "edit": True, "delete": True, "slash_commands": True,
        "max_message_length": 2000,
    },
    "telegram": {
        "text": True, "voice": True, "image": True, "video": True,
        "file": True, "embed": False, "buttons": True, "select_menu": False,
        "threads": True, "reactions": True, "typing": True,
        "edit": True, "delete": True, "slash_commands": True,
        "max_message_length": 4096,
    },
    "slack": {
        "text": True, "voice": False, "image": True, "video": False,
        "file": True, "embed": False, "buttons": True, "select_menu": True,
        "threads": True, "reactions": True, "typing": True,
        "edit": True, "delete": True, "slash_commands": True,
        "max_message_length": 40000,
    },
    "signal": {
        "text": True, "voice": False, "image": True, "video": True,
        "file": True, "embed": False, "buttons": False, "select_menu": False,
        "threads": False, "reactions": True, "typing": True,
        "edit": False, "delete": False, "slash_commands": False,
        "max_message_length": 65536,
    },
    "imessage": {
        "text": True, "voice": False, "image": True, "video": True,
        "file": True, "embed": False, "buttons": False, "select_menu": False,
        "threads": False, "reactions": True, "typing": False,
        "edit": False, "delete": False, "slash_commands": False,
        "max_message_length": 20000,
    },
    "whatsapp": {
        "text": True, "voice": True, "image": True, "video": True,
        "file": True, "embed": False, "buttons": True, "select_menu": True,
        "threads": False, "reactions": True, "typing": True,
        "edit": False, "delete": True, "slash_commands": False,
        "max_message_length": 65536,
    },
    "line": {
        "text": True, "voice": False, "image": True, "video": True,
        "file": False, "embed": False, "buttons": True, "select_menu": False,
        "threads": False, "reactions": False, "typing": False,
        "edit": False, "delete": False, "slash_commands": False,
        "max_message_length": 5000,
    },
}


def get_channel_capabilities(channel: str) -> dict[str, Any]:
    return CHANNEL_CAPABILITIES.get(channel, {})


def compare_channels() -> list[dict[str, Any]]:
    """Compare capabilities across all channels."""
    all_caps = set()
    for caps in CHANNEL_CAPABILITIES.values():
        all_caps.update(caps.keys())

    rows = []
    for cap in sorted(all_caps):
        row = {"capability": cap}
        for ch in CHANNEL_CAPABILITIES:
            row[ch] = CHANNEL_CAPABILITIES[ch].get(cap, False)
        rows.append(row)
    return rows


# ─── Model picker ───

async def interactive_model_picker(
    *,
    current_model: str = "",
    provider: str = "",
) -> str | None:
    """Interactive model picker."""
    from .deep import list_available_models
    models = list_available_models(provider=provider)
    if not models:
        print("  No models available")
        return None

    print("\n  Available models:")
    for i, m in enumerate(models):
        marker = "●" if m.id == current_model else "○"
        vision = "👁" if m.supports_vision else "  "
        tools = "🔧" if m.supports_tools else "  "
        think = "🧠" if m.supports_thinking else "  "
        cost = f"${m.cost_per_1m_input:.2f}/{m.cost_per_1m_output:.2f}"
        print(f"    {marker} {i+1}. {m.name:<25} {vision}{tools}{think} ctx:{m.context_window//1000}k  {cost}")

    try:
        choice = input(f"\n  Choice [{current_model}]: ").strip()
        if not choice:
            return current_model
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            return models[idx].id
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    return None

"""Commands — extended handlers: onboarding, doctor, auth, status.

Ported from bk/src/commands/ — large files:
doctor-config-flow.ts (~2100行), doctor-state-integrity.ts (~825行),
health.ts (~751行), agent.ts (~1152行),
onboard-non-interactive.ts, onboard-custom.ts (~825行),
onboard-channels.ts (~745行), onboard-auth.config-core.ts (~575行),
configure.wizard.ts (~702行), status.command.ts (~685行),
status-all/channels.ts (~659行), models/list.status-command.ts (~687行),
models/list.probe.ts (~620行), auth-choice.apply.api-providers.ts (~677行),
auth-choice.ts (x2), auth-choice-options.ts, auth-choice-prompt.ts,
auth-choice-inference.ts, auth-choice-legacy.ts,
auth-choice.model-check.ts, auth-choice.preferred-provider.ts,
auth-choice.apply.*.ts (15+), auth-order.ts, auth-token.ts,
channel-account-context.ts, channel-issues.ts,
config-validation.ts, daemon-install.ts, daemon-install-helpers.ts,
daemon-runtime.ts, dashboard.ts, delivery.ts,
diagnosis.ts, docs.ts, plugin-install.ts,
remote.ts, remove.ts, scan.ts,
sessions-table.ts, session-store.ts, session-store-targets.ts,
set-image.ts, signal-install.ts, skills-config.ts,
sandbox.ts, sandbox-display.ts, sandbox-explain.ts,
sandbox-formatters.ts, vllm-setup.ts, workspace.ts.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Doctor — config flow diagnosis ───

@dataclass
class DoctorCheck:
    name: str = ""
    status: str = "ok"  # "ok" | "warning" | "error" | "info"
    message: str = ""
    fix_command: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoctorReport:
    checks: list[DoctorCheck] = field(default_factory=list)
    overall: str = "ok"
    timestamp: str = ""

    @property
    def has_errors(self) -> bool:
        return any(c.status == "error" for c in self.checks)


async def run_doctor_config_flow(config: dict[str, Any]) -> list[DoctorCheck]:
    """Run config flow diagnostic checks."""
    checks = []

    # 1. Config file exists and is valid
    from ..config.paths import resolve_config_path
    config_path = resolve_config_path()
    if os.path.exists(config_path):
        checks.append(DoctorCheck(name="config_file", status="ok", message=f"Found: {config_path}"))
    else:
        checks.append(DoctorCheck(name="config_file", status="warning",
                                  message="No config file found", fix_command="openclaw setup"))

    # 2. Provider configured
    providers = config.get("providers", {}) or {}
    if providers:
        checks.append(DoctorCheck(name="provider", status="ok",
                                  message=f"Providers: {', '.join(providers.keys())}"))
    else:
        agents = config.get("agents", {}) or {}
        defaults = agents.get("defaults", {}) or {}
        model = defaults.get("model", "")
        if model:
            checks.append(DoctorCheck(name="provider", status="ok",
                                      message=f"Model configured: {model}"))
        else:
            checks.append(DoctorCheck(name="provider", status="error",
                                      message="No AI provider configured", fix_command="openclaw setup"))

    # 3. API key available
    api_key_found = False
    for env_var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                    "OPENROUTER_API_KEY", "XAI_API_KEY"):
        if os.environ.get(env_var):
            api_key_found = True
            break
    for p_cfg in providers.values():
        if isinstance(p_cfg, dict) and p_cfg.get("apiKey"):
            api_key_found = True
            break
    if api_key_found:
        checks.append(DoctorCheck(name="api_key", status="ok", message="API key found"))
    else:
        checks.append(DoctorCheck(name="api_key", status="error",
                                  message="No API key found", fix_command="openclaw login"))

    # 4. State directory
    from ..config.paths import resolve_state_dir
    state_dir = resolve_state_dir()
    if os.path.isdir(state_dir):
        checks.append(DoctorCheck(name="state_dir", status="ok", message=state_dir))
    else:
        checks.append(DoctorCheck(name="state_dir", status="info",
                                  message=f"Will be created: {state_dir}"))

    # 5. Config validation
    from ..config.validation import validate_config_object
    result = validate_config_object(config)
    if result.ok:
        msg = "Valid"
        if result.warnings:
            msg += f" ({len(result.warnings)} warnings)"
        checks.append(DoctorCheck(name="config_valid", status="ok", message=msg))
    else:
        checks.append(DoctorCheck(name="config_valid", status="error",
                                  message=f"{len(result.issues)} issue(s)"))

    return checks


async def run_doctor_state_integrity(config: dict[str, Any]) -> list[DoctorCheck]:
    """Check state directory integrity."""
    checks = []
    from ..config.paths import resolve_state_dir, resolve_sessions_dir, resolve_logs_dir

    state_dir = resolve_state_dir()

    # Sessions dir
    sessions_dir = resolve_sessions_dir()
    if os.path.isdir(sessions_dir):
        count = len([d for d in os.listdir(sessions_dir) if os.path.isdir(os.path.join(sessions_dir, d))])
        checks.append(DoctorCheck(name="sessions", status="ok", message=f"{count} session(s)"))
    else:
        checks.append(DoctorCheck(name="sessions", status="info", message="No sessions yet"))

    # Logs dir
    logs_dir = resolve_logs_dir()
    if os.path.isdir(logs_dir):
        log_files = [f for f in os.listdir(logs_dir) if f.endswith(".log") or f.endswith(".jsonl")]
        total_size = sum(os.path.getsize(os.path.join(logs_dir, f)) for f in log_files if os.path.isfile(os.path.join(logs_dir, f)))
        checks.append(DoctorCheck(name="logs", status="ok",
                                  message=f"{len(log_files)} file(s), {total_size // 1024}KB"))
    else:
        checks.append(DoctorCheck(name="logs", status="info", message="No logs yet"))

    # Disk space
    try:
        stat = os.statvfs(state_dir if os.path.exists(state_dir) else os.path.expanduser("~"))
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
        status = "ok" if free_gb > 1 else "warning" if free_gb > 0.1 else "error"
        checks.append(DoctorCheck(name="disk_space", status=status, message=f"{free_gb:.1f}GB free"))
    except Exception:
        checks.append(DoctorCheck(name="disk_space", status="info", message="Unable to check"))

    return checks


# ─── Auth choice — provider authentication ───

@dataclass
class AuthChoice:
    """Resolved authentication choice for a provider."""
    provider: str = ""
    auth_method: str = ""  # "api-key" | "oauth" | "browser" | "copilot-proxy"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    is_valid: bool = False

PROVIDER_AUTH_DEFAULTS = {
    "anthropic": {"env": "ANTHROPIC_API_KEY", "model": "claude-sonnet-4-20250514", "base_url": "https://api.anthropic.com"},
    "openai": {"env": "OPENAI_API_KEY", "model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
    "google": {"env": "GEMINI_API_KEY", "model": "gemini-2.0-flash", "base_url": ""},
    "openrouter": {"env": "OPENROUTER_API_KEY", "model": "anthropic/claude-sonnet-4-20250514", "base_url": "https://openrouter.ai/api/v1"},
    "xai": {"env": "XAI_API_KEY", "model": "grok-3", "base_url": "https://api.x.ai/v1"},
    "minimax": {"env": "MINIMAX_API_KEY", "model": "minimax-01", "base_url": "https://api.minimax.chat/v1"},
    "huggingface": {"env": "HF_TOKEN", "model": "", "base_url": ""},
    "volcengine": {"env": "VOLCENGINE_API_KEY", "model": "", "base_url": ""},
    "byteplus": {"env": "BYTEPLUS_API_KEY", "model": "", "base_url": ""},
    "vllm": {"env": "VLLM_API_KEY", "model": "", "base_url": "http://localhost:8000/v1"},
    "qwen-portal": {"env": "DASHSCOPE_API_KEY", "model": "qwen-max", "base_url": ""},
}


def resolve_auth_choice(
    provider: str,
    config: dict[str, Any] | None = None,
) -> AuthChoice:
    """Resolve authentication for a provider."""
    defaults = PROVIDER_AUTH_DEFAULTS.get(provider.lower(), {})
    env_var = defaults.get("env", "")
    
    # Check env
    api_key = os.environ.get(env_var, "") if env_var else ""
    
    # Check config
    if not api_key and config:
        providers = config.get("providers", {}) or {}
        p_cfg = providers.get(provider, {}) or {}
        cfg_key = p_cfg.get("apiKey", "")
        if isinstance(cfg_key, str) and cfg_key and not cfg_key.startswith("${"):
            api_key = cfg_key
    
    return AuthChoice(
        provider=provider,
        auth_method="api-key" if api_key else "",
        api_key=api_key,
        model=defaults.get("model", ""),
        base_url=defaults.get("base_url", ""),
        is_valid=bool(api_key),
    )


def infer_provider_from_model(model: str) -> str:
    """Infer provider from model name."""
    model_lower = model.lower()
    if any(x in model_lower for x in ("claude", "haiku", "sonnet", "opus")):
        return "anthropic"
    if any(x in model_lower for x in ("gpt", "o1", "o3", "dall-e", "whisper")):
        return "openai"
    if any(x in model_lower for x in ("gemini", "palm")):
        return "google"
    if any(x in model_lower for x in ("grok",)):
        return "xai"
    if any(x in model_lower for x in ("minimax",)):
        return "minimax"
    if any(x in model_lower for x in ("qwen",)):
        return "qwen-portal"
    if "/" in model and not model.startswith("http"):
        return "openrouter"
    return ""


# ─── Onboard — channel configuration ───

CHANNEL_SETUP_STEPS = {
    "discord": [
        "Create a Discord bot at https://discord.com/developers",
        "Copy the bot token",
        "Invite the bot to your server",
        "Set the bot token in config",
    ],
    "telegram": [
        "Talk to @BotFather on Telegram",
        "Create a new bot with /newbot",
        "Copy the bot token",
        "Set the bot token in config",
    ],
    "slack": [
        "Create a Slack app at https://api.slack.com/apps",
        "Add Bot Token Scopes (chat:write, app_mentions:read)",
        "Install to workspace",
        "Copy Bot User OAuth Token",
    ],
    "signal": [
        "Install signal-cli",
        "Register or link your phone number",
        "Configure the phone number in config",
    ],
    "whatsapp": [
        "Install the WhatsApp Web bridge",
        "Scan the QR code with your phone",
    ],
    "line": [
        "Create a LINE Developers account",
        "Create a Messaging API channel",
        "Copy the Channel Access Token",
    ],
}


async def onboard_channel_interactive(channel: str) -> dict[str, Any] | None:
    """Interactive channel setup."""
    steps = CHANNEL_SETUP_STEPS.get(channel)
    if not steps:
        print(f"  Unknown channel: {channel}")
        return None

    print(f"\n  Setting up {channel.title()}:")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")
    print()

    # Collect token
    try:
        import getpass
        token = getpass.getpass(f"  {channel.title()} token: ").strip()
        if not token:
            print("  ⚠ No token provided, skipping")
            return None
        return {"channel": channel, "token": token}
    except (EOFError, KeyboardInterrupt):
        return None


# ─── Status — extended status display ───

@dataclass
class ChannelStatus:
    name: str = ""
    status: str = "unknown"
    connected: bool = False
    account_name: str = ""
    last_message_ms: int = 0
    error: str | None = None


async def gather_channel_statuses(config: dict[str, Any]) -> list[ChannelStatus]:
    """Gather status of all configured channels."""
    statuses = []
    channels = config.get("channels", {}) or {}
    for name, ch_cfg in channels.items():
        if not isinstance(ch_cfg, dict):
            continue
        statuses.append(ChannelStatus(
            name=name,
            status="enabled" if ch_cfg.get("enabled", True) else "disabled",
            connected=False,
            account_name=str(ch_cfg.get("accountName", "")),
        ))
    return statuses


@dataclass
class ModelProbeResult:
    model: str = ""
    provider: str = ""
    reachable: bool = False
    latency_ms: int = 0
    error: str | None = None


async def probe_model(model: str, provider: str, *, timeout_ms: int = 10000) -> ModelProbeResult:
    """Probe a model for reachability."""
    start = int(time.time() * 1000)
    try:
        auth = resolve_auth_choice(provider)
        if not auth.is_valid:
            return ModelProbeResult(model=model, provider=provider, error="No API key")
        
        import aiohttp
        url = f"{auth.base_url}/models" if auth.base_url else ""
        if not url:
            return ModelProbeResult(model=model, provider=provider, error="No base URL")
        
        headers = {"Authorization": f"Bearer {auth.api_key}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                  timeout=aiohttp.ClientTimeout(total=timeout_ms/1000)) as resp:
                latency = int(time.time() * 1000) - start
                return ModelProbeResult(
                    model=model, provider=provider,
                    reachable=(resp.status == 200),
                    latency_ms=latency,
                )
    except Exception as e:
        latency = int(time.time() * 1000) - start
        return ModelProbeResult(model=model, provider=provider, error=str(e), latency_ms=latency)


# ─── Daemon install helpers ───

async def install_daemon_service(*, mode: str = "auto") -> bool:
    """Install the daemon as a system service."""
    import platform
    system = platform.system()
    
    if mode == "auto":
        mode = "launchd" if system == "Darwin" else "systemd"
    
    if mode == "systemd":
        from ..daemon import generate_systemd_unit, install_systemd_service
        unit = generate_systemd_unit()
        return install_systemd_service(unit)
    elif mode == "launchd":
        from ..daemon import generate_launchd_plist
        plist = generate_launchd_plist()
        plist_path = os.path.expanduser("~/Library/LaunchAgents/ai.openclaw.gateway.plist")
        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
        with open(plist_path, "w") as f:
            f.write(plist)
        import subprocess
        subprocess.run(["launchctl", "load", plist_path], capture_output=True)
        return True
    
    return False


# ─── Sandbox ───

@dataclass
class SandboxConfig:
    mode: str = "none"  # "none" | "docker" | "e2b"
    image: str = "ubuntu:22.04"
    timeout_ms: int = 300_000
    memory_mb: int = 512
    cpu_count: int = 1
    network: bool = False
    volumes: list[str] = field(default_factory=list)


def resolve_sandbox_config(config: dict[str, Any]) -> SandboxConfig:
    sandbox = config.get("sandbox", {}) or {}
    return SandboxConfig(
        mode=sandbox.get("mode", "none"),
        image=sandbox.get("image", "ubuntu:22.04"),
        timeout_ms=int(sandbox.get("timeoutMs", 300_000)),
        memory_mb=int(sandbox.get("memoryMb", 512)),
        network=bool(sandbox.get("network", False)),
    )


# ─── Workspace ───

def resolve_workspace_dir(config: dict[str, Any], *, cwd: str = "") -> str:
    """Resolve the workspace directory."""
    workspace = config.get("workspace", {}) or {}
    configured = workspace.get("dir", "")
    if configured:
        return os.path.expanduser(configured)
    return cwd or os.getcwd()

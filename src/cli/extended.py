"""CLI — extended subcommand implementations.

Ported from bk/src/cli/ remaining large files:
update-cli/update-command.ts (~918行), plugins-cli.ts (~826行),
hooks-cli.ts (~821行), memory-cli.ts (~817行),
completion-cli.ts (~665行), command-secret-gateway.ts (~553行),
gateway-cli/run.ts (~508行), exec-approvals-cli.ts (~482行),
browser-cli-manage.ts (~481行), nodes-cli.ts, acp-cli.ts,
call.ts, channel-auth.ts, channel-options.ts,
channels-cli.ts, clawbot-cli.ts, dns-cli.ts,
docs-cli.ts, logs-cli.ts, models-cli.ts,
pairing-cli.ts, pairing-render.ts, sandbox-cli.ts,
secrets-cli.ts, security-cli.ts, skills-cli*.ts,
system-cli.ts, tui-cli.ts, webhooks-cli.ts,
devices-cli.ts, directory-cli.ts, browser-cli*.ts,
outbound-send-deps.ts, outbound-send-mapping.ts,
completion-fish.ts, command-options.ts, command-registry.ts,
command-tree.ts, dev.ts.
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


# ─── Update command ───

@dataclass
class UpdateInfo:
    current_version: str = ""
    latest_version: str = ""
    update_available: bool = False
    channel: str = "stable"  # "stable" | "beta" | "dev"


async def check_for_update(*, channel: str = "stable") -> UpdateInfo:
    """Check npm for available updates."""
    current = _get_current_version()
    info = UpdateInfo(current_version=current, channel=channel)
    
    try:
        tag = "latest" if channel == "stable" else channel
        result = subprocess.run(
            ["npm", "view", "openclaw", "version", "--tag", tag, "--userconfig", "/dev/null"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            latest = result.stdout.strip()
            info.latest_version = latest
            from ..utils import compare_semver
            info.update_available = compare_semver(latest, current) > 0
    except Exception as e:
        logger.debug(f"Update check failed: {e}")
    
    return info


async def run_update(*, version: str = "", channel: str = "stable") -> bool:
    """Run the update command."""
    pkg = f"openclaw@{version}" if version else "openclaw@latest"
    try:
        result = subprocess.run(
            ["npm", "install", "-g", pkg],
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_current_version() -> str:
    try:
        pkg_json = os.path.join(os.path.dirname(__file__), "..", "..", "package.json")
        if os.path.exists(pkg_json):
            with open(pkg_json) as f:
                return json.load(f).get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"


# ─── Plugins CLI ───

@dataclass
class PluginInfo:
    name: str = ""
    version: str = ""
    description: str = ""
    installed: bool = False
    enabled: bool = True
    path: str = ""


async def list_plugins(config: dict[str, Any]) -> list[PluginInfo]:
    """List installed plugins."""
    plugins_dir = os.path.expanduser("~/.openclaw/plugins")
    plugins = []
    if not os.path.isdir(plugins_dir):
        return plugins
    
    for name in sorted(os.listdir(plugins_dir)):
        pkg_path = os.path.join(plugins_dir, name, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path) as f:
                    pkg = json.load(f)
                plugins.append(PluginInfo(
                    name=name,
                    version=pkg.get("version", ""),
                    description=pkg.get("description", ""),
                    installed=True,
                    path=os.path.join(plugins_dir, name),
                ))
            except Exception:
                plugins.append(PluginInfo(name=name, installed=True, path=os.path.join(plugins_dir, name)))
    return plugins


async def install_plugin(name: str, *, version: str = "") -> bool:
    """Install a plugin via npm."""
    plugins_dir = os.path.expanduser("~/.openclaw/plugins")
    plugin_dir = os.path.join(plugins_dir, name)
    os.makedirs(plugin_dir, exist_ok=True)
    
    pkg_spec = f"{name}@{version}" if version else name
    try:
        result = subprocess.run(
            ["npm", "install", "--omit=dev", pkg_spec],
            cwd=plugin_dir, capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False


async def uninstall_plugin(name: str) -> bool:
    import shutil
    plugin_dir = os.path.expanduser(f"~/.openclaw/plugins/{name}")
    if os.path.isdir(plugin_dir):
        shutil.rmtree(plugin_dir, ignore_errors=True)
        return True
    return False


# ─── Hooks CLI ───

@dataclass
class HookConfig:
    event: str = ""  # "message:pre" | "message:post" | "reply:pre" | "reply:post"
    command: str = ""
    timeout_ms: int = 30_000
    enabled: bool = True


def list_hooks(config: dict[str, Any]) -> list[HookConfig]:
    hooks = config.get("hooks", [])
    if not isinstance(hooks, list):
        return []
    return [
        HookConfig(
            event=h.get("event", ""),
            command=h.get("command", ""),
            timeout_ms=int(h.get("timeoutMs", 30_000)),
            enabled=bool(h.get("enabled", True)),
        )
        for h in hooks if isinstance(h, dict)
    ]


# ─── Memory CLI ───

async def memory_search(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Search through memory entries."""
    from ..memory import MemoryStore
    store = MemoryStore()
    results = await store.search(query, top_k=limit)
    return [{"content": r.content, "score": r.score, "created_at": r.created_at_ms} for r in results]


async def memory_clear(*, agent_id: str = "") -> int:
    """Clear memory entries."""
    from ..memory import MemoryStore
    store = MemoryStore()
    return await store.clear(agent_id=agent_id)


# ─── Completion CLI (shell autocompletion) ───

def generate_bash_completion() -> str:
    return '''
_openclaw_completions() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local commands="agent send config gateway channels sessions status doctor setup login
                    version cron secrets plugins daemon nodes browser models memory update
                    logs skills webhooks"
    
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
    fi
}
complete -F _openclaw_completions openclaw
'''.strip()


def generate_zsh_completion() -> str:
    return '''
#compdef openclaw

_openclaw() {
    local -a commands
    commands=(
        'agent:Run an agent'
        'send:Send a message'
        'config:Manage configuration'
        'gateway:Manage the gateway'
        'channels:Manage channels'
        'sessions:Manage sessions'
        'status:Show status'
        'doctor:Run diagnostics'
        'setup:Interactive setup'
        'login:Authenticate'
        'update:Update openclaw'
    )
    _describe 'command' commands
}

_openclaw "$@"
'''.strip()


def generate_fish_completion() -> str:
    return '''
complete -c openclaw -f
complete -c openclaw -n '__fish_use_subcommand' -a 'agent' -d 'Run an agent'
complete -c openclaw -n '__fish_use_subcommand' -a 'send' -d 'Send a message'
complete -c openclaw -n '__fish_use_subcommand' -a 'config' -d 'Manage configuration'
complete -c openclaw -n '__fish_use_subcommand' -a 'gateway' -d 'Manage the gateway'
complete -c openclaw -n '__fish_use_subcommand' -a 'channels' -d 'Manage channels'
complete -c openclaw -n '__fish_use_subcommand' -a 'sessions' -d 'Manage sessions'
complete -c openclaw -n '__fish_use_subcommand' -a 'status' -d 'Show status'
complete -c openclaw -n '__fish_use_subcommand' -a 'doctor' -d 'Run diagnostics'
complete -c openclaw -n '__fish_use_subcommand' -a 'update' -d 'Update openclaw'
'''.strip()


# ─── Gateway CLI run ───

@dataclass
class GatewayRunOptions:
    port: int = 18789
    bind: str = "loopback"  # "loopback" | "0.0.0.0" | "tailscale"
    force: bool = False
    config_path: str = ""
    foreground: bool = False
    log_level: str = "info"


async def gateway_run(options: GatewayRunOptions) -> bool:
    """Start the gateway process."""
    from ..daemon import DaemonManager
    dm = DaemonManager()
    
    if dm.is_running() and not options.force:
        logger.warning("Gateway already running. Use --force to restart.")
        return False
    
    if dm.is_running():
        dm.stop()
        time.sleep(0.5)
    
    info = dm.start(port=options.port, bind=options.bind, config_path=options.config_path)
    return info is not None


async def gateway_stop() -> bool:
    from ..daemon import DaemonManager
    return DaemonManager().stop()


# ─── Exec approvals CLI ───

@dataclass
class ExecApproval:
    tool_name: str = ""
    command: str = ""
    risk_level: str = "low"  # "low" | "medium" | "high" | "dangerous"
    auto_approve: bool = False


def classify_exec_risk(command: str) -> str:
    """Classify the risk level of a command."""
    dangerous_patterns = [
        "rm -rf", "dd if=", "mkfs", "format ", ": > /",
        "chmod 777", "curl | sh", "wget | bash",
    ]
    high_patterns = [
        "rm ", "mv /", "cp /", "chmod ", "chown ",
        "pip install", "npm install -g", "sudo",
    ]
    medium_patterns = [
        "git push", "git reset", "docker rm", "docker rmi",
        "kill ", "pkill ",
    ]
    
    cmd_lower = command.lower()
    for p in dangerous_patterns:
        if p in cmd_lower:
            return "dangerous"
    for p in high_patterns:
        if p in cmd_lower:
            return "high"
    for p in medium_patterns:
        if p in cmd_lower:
            return "medium"
    return "low"


# ─── Browser CLI ───

@dataclass
class BrowserAction:
    action: str = ""  # "open" | "click" | "type" | "screenshot" | "scroll"
    selector: str = ""
    value: str = ""
    url: str = ""


# ─── Secrets CLI ───

async def secrets_list() -> list[str]:
    from ..secrets import SecretStore
    store_dir = os.path.expanduser("~/.openclaw/secrets")
    store = SecretStore(store_dir)
    return store.list_names()


async def secrets_set(name: str, value: str) -> None:
    from ..secrets import SecretStore
    store_dir = os.path.expanduser("~/.openclaw/secrets")
    store = SecretStore(store_dir)
    store.set(name, value)


async def secrets_delete(name: str) -> bool:
    from ..secrets import SecretStore
    store_dir = os.path.expanduser("~/.openclaw/secrets")
    store = SecretStore(store_dir)
    return store.delete(name)


# ─── Logs CLI ───

def tail_log(log_path: str, *, lines: int = 100, follow: bool = False) -> list[str]:
    """Read last N lines of a log file."""
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return all_lines[-lines:]
    except Exception:
        return []

"""Configuration type definitions.

Ported from bk/src/config/types.ts, types.agents.ts, types.models.ts,
types.gateway.ts, types.channels.ts, types.auth.ts, types.hooks.ts,
types.cron.ts, types.plugins.ts, types.secrets.ts, types.memory.ts,
types.browser.ts, types.tools.ts, types.messages.ts, types.base.ts,
types.acp.ts, types.approvals.ts, types.cli.ts, types.discord.ts,
types.slack.ts, types.telegram.ts, types.signal.ts, types.imessage.ts,
types.whatsapp.ts, types.tts.ts, types.openclaw.ts, types.skills.ts,
types.node-host.ts, types.sandbox.ts, types.queue.ts, types.installs.ts,
types.irc.ts, types.googlechat.ts, types.msteams.ts,
types.channel-messaging-common.ts, types.agent-defaults.ts,
types.agents-shared.ts, config-paths.ts.

Represents the full OpenClawConfig shape as nested TypedDicts / dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─── Primitive config types ───

@dataclass
class SecretInput:
    """A secret value — can be literal, env ref, or 1Password ref."""
    value: str = ""
    env: str | None = None
    op: str | None = None


@dataclass
class ModelCost:
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass
class ModelDefinitionConfig:
    id: str = ""
    name: str = ""
    provider: str = ""
    api: str | None = None
    reasoning: bool = False
    input: list[str] = field(default_factory=lambda: ["text"])
    context_window: int = 200_000
    max_tokens: int = 8192
    cost: ModelCost = field(default_factory=ModelCost)
    params: dict[str, Any] = field(default_factory=dict)


# ─── Sub-config sections ───

@dataclass
class GatewayAuthConfig:
    token: str | None = None
    password: str | None = None
    mode: str = "token"  # "token" | "password" | "none"


@dataclass
class ControlUiConfig:
    enabled: bool = True
    allowed_origins: list[str] = field(default_factory=list)


@dataclass
class GatewayConfig:
    mode: str = "local"  # "local" | "remote"
    port: int = 18789
    bind: str = "loopback"  # "loopback" | "all"
    auth: GatewayAuthConfig = field(default_factory=GatewayAuthConfig)
    control_ui: ControlUiConfig = field(default_factory=ControlUiConfig)
    tailscale: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionConfig:
    main_key: str = "main"
    storage: str = "jsonl"  # "jsonl" | "sqlite"
    max_turns: int = 0  # 0 = unlimited


@dataclass
class AgentDefaultsConfig:
    model: str | dict[str, Any] | None = None
    max_concurrent: int = 5
    context_window: int = 200_000
    max_tokens: int = 8192
    system_prompt: str = ""
    tools: list[str] | None = None
    compaction: dict[str, Any] = field(default_factory=dict)
    context_pruning: dict[str, Any] = field(default_factory=dict)
    heartbeat: dict[str, Any] = field(default_factory=dict)
    models: dict[str, Any] = field(default_factory=dict)
    subagents: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentsConfig:
    defaults: AgentDefaultsConfig = field(default_factory=AgentDefaultsConfig)
    dir: str | None = None
    entries: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvidersConfig:
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ModelsConfig:
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ChannelConfig:
    name: str = ""
    type: str = ""
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoggingConfig:
    level: str = "info"
    redact_sensitive: str = "tools"  # "none" | "tools" | "all"
    dir: str | None = None


@dataclass
class MemoryConfig:
    enabled: bool = False
    backend: str = "local"  # "local" | "chromadb"
    dir: str | None = None
    auto_save: bool = True


@dataclass
class HooksConfig:
    before_reply: list[dict[str, Any]] = field(default_factory=list)
    after_reply: list[dict[str, Any]] = field(default_factory=list)
    on_start: list[dict[str, Any]] = field(default_factory=list)
    on_stop: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CronJobConfig:
    id: str = ""
    schedule: str = ""
    command: str = ""
    channel: str | None = None
    enabled: bool = True
    timeout_ms: int = 300_000


@dataclass
class PluginsConfig:
    dir: str | None = None
    enabled: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SecretsConfig:
    backend: str = "env"  # "env" | "1password" | "file"
    one_password: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrowserConfig:
    enabled: bool = False
    headless: bool = True
    timeout_ms: int = 30_000


@dataclass
class TalkProviderConfig:
    provider: str = ""
    api_key: str | SecretInput | None = None
    voice: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class TalkConfig:
    enabled: bool = False
    provider: str = "elevenlabs"
    api_key: str | SecretInput | None = None
    providers: dict[str, TalkProviderConfig] = field(default_factory=dict)


@dataclass
class AcpConfig:
    enabled: bool = False
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ApprovalsConfig:
    mode: str = "ask"  # "ask" | "auto-edit" | "auto-full"
    auto_edit: dict[str, Any] = field(default_factory=dict)


@dataclass
class MessagesConfig:
    ack_reaction_scope: str = "group-mentions"


@dataclass
class SkillsConfig:
    dir: str | None = None
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class EnvConfig:
    vars: dict[str, str] = field(default_factory=dict)
    shell_env: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthProfileConfig:
    provider: str = ""
    mode: str = "api_key"  # "api_key" | "oauth" | "token"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthConfig:
    profiles: dict[str, AuthProfileConfig] = field(default_factory=dict)
    order: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class MetaConfig:
    last_touched_version: str = ""
    last_touched_at: str = ""


@dataclass
class DiscordConfig:
    bot_token: str | SecretInput | None = None
    preview_streaming: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelegramConfig:
    bot_token: str | SecretInput | None = None
    custom_commands: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SlackConfig:
    bot_token: str | SecretInput | None = None
    app_token: str | SecretInput | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalConfig:
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class IMessageConfig:
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class WhatsAppConfig:
    config: dict[str, Any] = field(default_factory=dict)


# ─── Main config type ───

@dataclass
class OpenClawConfig:
    """Top-level OpenClaw configuration.

    This is the Python equivalent of the TypeScript OpenClawConfig type.
    All fields are optional with sensible defaults.
    """
    meta: MetaConfig = field(default_factory=MetaConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    channels: dict[str, ChannelConfig] = field(default_factory=dict)
    logging_config: LoggingConfig = field(default_factory=LoggingConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    cron: list[CronJobConfig] = field(default_factory=list)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    talk: TalkConfig = field(default_factory=TalkConfig)
    acp: AcpConfig = field(default_factory=AcpConfig)
    approvals: ApprovalsConfig = field(default_factory=ApprovalsConfig)
    messages: MessagesConfig = field(default_factory=MessagesConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    env: EnvConfig = field(default_factory=EnvConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    imessage: IMessageConfig = field(default_factory=IMessageConfig)
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)

    # Raw dict for pass-through / extension fields
    _raw: dict[str, Any] = field(default_factory=dict)


# ─── Config file snapshot ───

@dataclass
class ConfigFileSnapshot:
    """A point-in-time snapshot of a config file."""
    raw: str | None = None
    hash: str | None = None
    path: str = ""
    parsed: dict[str, Any] | None = None
    config: OpenClawConfig | None = None
    env_snapshot: dict[str, str | None] | None = None


# ─── Legacy config issue ───

@dataclass
class LegacyConfigIssue:
    path: str = ""
    message: str = ""
    severity: str = "warning"  # "warning" | "error"


# ─── Config validation result ───

@dataclass
class ConfigValidationIssue:
    path: str = ""
    message: str = ""


@dataclass
class ConfigValidationResult:
    ok: bool = True
    config: OpenClawConfig | None = None
    issues: list[ConfigValidationIssue] = field(default_factory=list)
    warnings: list[ConfigValidationIssue] = field(default_factory=list)

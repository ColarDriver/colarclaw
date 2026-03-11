"""Agent identity — ported from bk/src/agents/identity.ts.

Resolves agent identity (name, emoji), message prefixes,
ack reactions, response prefixes, and human delay config.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_ACK_REACTION = "👀"


@dataclass
class IdentityConfig:
    name: str | None = None
    emoji: str | None = None
    theme: str | None = None
    creature: str | None = None
    vibe: str | None = None
    avatar: str | None = None


@dataclass
class HumanDelayConfig:
    mode: str | None = None
    min_ms: int | None = None
    max_ms: int | None = None


@dataclass
class EffectiveMessagesConfig:
    message_prefix: str
    response_prefix: str | None = None


def _get_channel_config(cfg: dict[str, Any], channel: str) -> dict[str, Any] | None:
    channels = cfg.get("channels")
    if not isinstance(channels, dict):
        return None
    value = channels.get(channel)
    if isinstance(value, dict):
        return value
    return None


def _resolve_agent_config(cfg: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    """Resolve agent-specific config section."""
    agents_cfg = cfg.get("agents", {})
    if not isinstance(agents_cfg, dict):
        return None
    # Check agent-specific overrides
    overrides = agents_cfg.get("overrides", {})
    if isinstance(overrides, dict) and agent_id in overrides:
        return overrides[agent_id]
    return agents_cfg.get("defaults")


def resolve_agent_identity(
    cfg: dict[str, Any],
    agent_id: str,
) -> IdentityConfig | None:
    """Resolve identity config for an agent."""
    agent_config = _resolve_agent_config(cfg, agent_id)
    if not agent_config:
        return None
    identity_raw = agent_config.get("identity")
    if not isinstance(identity_raw, dict):
        return None
    return IdentityConfig(
        name=identity_raw.get("name"),
        emoji=identity_raw.get("emoji"),
        theme=identity_raw.get("theme"),
        creature=identity_raw.get("creature"),
        vibe=identity_raw.get("vibe"),
        avatar=identity_raw.get("avatar"),
    )


def resolve_ack_reaction(
    cfg: dict[str, Any],
    agent_id: str,
    channel: str | None = None,
    account_id: str | None = None,
) -> str:
    """Resolve the ack reaction emoji for an agent with channel/account overrides."""
    # L1: Channel account level
    if channel and account_id:
        channel_cfg = _get_channel_config(cfg, channel)
        if channel_cfg:
            accounts = channel_cfg.get("accounts", {})
            if isinstance(accounts, dict) and account_id in accounts:
                account_reaction = accounts[account_id].get("ackReaction")
                if account_reaction is not None:
                    return str(account_reaction).strip()

    # L2: Channel level
    if channel:
        channel_cfg = _get_channel_config(cfg, channel)
        if channel_cfg:
            channel_reaction = channel_cfg.get("ackReaction")
            if channel_reaction is not None:
                return str(channel_reaction).strip()

    # L3: Global messages level
    messages = cfg.get("messages", {})
    if isinstance(messages, dict):
        configured = messages.get("ackReaction")
        if configured is not None:
            return str(configured).strip()

    # L4: Agent identity emoji fallback
    identity = resolve_agent_identity(cfg, agent_id)
    if identity and identity.emoji:
        return identity.emoji.strip()

    return DEFAULT_ACK_REACTION


def resolve_identity_name_prefix(
    cfg: dict[str, Any],
    agent_id: str,
) -> str | None:
    identity = resolve_agent_identity(cfg, agent_id)
    if not identity or not identity.name:
        return None
    name = identity.name.strip()
    if not name:
        return None
    return f"[{name}]"


def resolve_identity_name(
    cfg: dict[str, Any],
    agent_id: str,
) -> str | None:
    """Returns the identity name without brackets."""
    identity = resolve_agent_identity(cfg, agent_id)
    if not identity or not identity.name:
        return None
    return identity.name.strip() or None


def resolve_message_prefix(
    cfg: dict[str, Any],
    agent_id: str,
    configured: str | None = None,
    has_allow_from: bool = False,
    fallback: str | None = None,
) -> str:
    """Resolve message prefix with fallback hierarchy."""
    effective = configured
    if effective is None:
        messages = cfg.get("messages", {})
        if isinstance(messages, dict):
            effective = messages.get("messagePrefix")

    if effective is not None:
        return str(effective)

    if has_allow_from:
        return ""

    return resolve_identity_name_prefix(cfg, agent_id) or fallback or "[openclaw]"


def resolve_response_prefix(
    cfg: dict[str, Any],
    agent_id: str,
    channel: str | None = None,
    account_id: str | None = None,
) -> str | None:
    """Resolve response prefix with hierarchical overrides."""
    # L1: Channel account level
    if channel and account_id:
        channel_cfg = _get_channel_config(cfg, channel)
        if channel_cfg:
            accounts = channel_cfg.get("accounts", {})
            if isinstance(accounts, dict) and account_id in accounts:
                prefix = accounts[account_id].get("responsePrefix")
                if prefix is not None:
                    if prefix == "auto":
                        return resolve_identity_name_prefix(cfg, agent_id)
                    return str(prefix)

    # L2: Channel level
    if channel:
        channel_cfg = _get_channel_config(cfg, channel)
        if channel_cfg:
            prefix = channel_cfg.get("responsePrefix")
            if prefix is not None:
                if prefix == "auto":
                    return resolve_identity_name_prefix(cfg, agent_id)
                return str(prefix)

    # L4: Global level
    messages = cfg.get("messages", {})
    if isinstance(messages, dict):
        configured = messages.get("responsePrefix")
        if configured is not None:
            if configured == "auto":
                return resolve_identity_name_prefix(cfg, agent_id)
            return str(configured)

    return None


def resolve_effective_messages_config(
    cfg: dict[str, Any],
    agent_id: str,
    has_allow_from: bool = False,
    fallback_message_prefix: str | None = None,
    channel: str | None = None,
    account_id: str | None = None,
) -> EffectiveMessagesConfig:
    return EffectiveMessagesConfig(
        message_prefix=resolve_message_prefix(
            cfg, agent_id,
            has_allow_from=has_allow_from,
            fallback=fallback_message_prefix,
        ),
        response_prefix=resolve_response_prefix(
            cfg, agent_id,
            channel=channel,
            account_id=account_id,
        ),
    )


def resolve_human_delay_config(
    cfg: dict[str, Any],
    agent_id: str,
) -> HumanDelayConfig | None:
    """Resolve human delay simulation config for an agent."""
    defaults = cfg.get("agents", {}).get("defaults", {}).get("humanDelay")
    agent_config = _resolve_agent_config(cfg, agent_id)
    overrides = agent_config.get("humanDelay") if agent_config else None

    if not defaults and not overrides:
        return None

    defaults = defaults or {}
    overrides = overrides or {}

    return HumanDelayConfig(
        mode=overrides.get("mode") or defaults.get("mode"),
        min_ms=overrides.get("minMs") or defaults.get("minMs"),
        max_ms=overrides.get("maxMs") or defaults.get("maxMs"),
    )

"""Channels plugins.onboarding — ported from bk/src/channels/plugins/onboarding/*.ts.

Channel onboarding flow support: setup helpers, per-channel onboarding steps,
and channel access configuration.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("channels.plugins.onboarding")


# ─── onboarding-types.ts ───

@dataclass
class OnboardingStep:
    id: str = ""
    title: str = ""
    description: str = ""
    required: bool = True
    completed: bool = False


@dataclass
class OnboardingFlow:
    channel: str = ""
    account_id: str = ""
    steps: list[OnboardingStep] = field(default_factory=list)
    completed: bool = False


# ─── channel-access.ts ───

@dataclass
class ChannelAccessConfig:
    channel: str = ""
    account_id: str = ""
    dm_policy: str = "open"  # "open" | "allowlist" | "paired"
    allow_from: list[str] = field(default_factory=list)
    allow_text_commands: bool = True
    require_mention: bool = True


def resolve_channel_access(
    cfg: dict[str, Any],
    channel: str,
    account_id: str = "",
) -> ChannelAccessConfig:
    """Resolve channel access configuration."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})

    result = ChannelAccessConfig(channel=channel, account_id=account_id)

    # DM policy
    dm = channel_cfg.get("dm", {})
    result.dm_policy = dm.get("policy", channel_cfg.get("dmPolicy", "open"))
    result.allow_from = [str(v).strip() for v in (
        dm.get("allowFrom", channel_cfg.get("allowFrom", []))
    ) if str(v).strip()]

    # Commands
    result.allow_text_commands = channel_cfg.get("allowTextCommands", True)

    # Mention
    groups = channel_cfg.get("groups", {})
    result.require_mention = groups.get("requireMention", True)

    return result


# ─── helpers.ts ───

@dataclass
class OnboardingHint:
    channel: str = ""
    title: str = ""
    message: str = ""
    docs_url: str = ""


def get_onboarding_hints(channel: str) -> list[OnboardingHint]:
    """Get onboarding hints for a channel."""
    hints: dict[str, list[OnboardingHint]] = {
        "telegram": [
            OnboardingHint(
                channel="telegram",
                title="Create a Telegram bot",
                message="Open @BotFather on Telegram and create a new bot to get an API token.",
                docs_url="https://docs.openclaw.ai/channels/telegram",
            ),
        ],
        "discord": [
            OnboardingHint(
                channel="discord",
                title="Create a Discord application",
                message="Go to the Discord Developer Portal and create a new application with a bot token.",
                docs_url="https://docs.openclaw.ai/channels/discord",
            ),
        ],
        "slack": [
            OnboardingHint(
                channel="slack",
                title="Create a Slack app",
                message="Create a Slack app with Socket Mode enabled.",
                docs_url="https://docs.openclaw.ai/channels/slack",
            ),
        ],
    }
    return hints.get(channel, [])

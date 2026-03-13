"""Channels plugins.onboarding_types — ported from bk/src/channels/plugins/onboarding-types.ts.

Onboarding type definitions and adapter interfaces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class OnboardingStatus:
    channel: str = ""
    configured: bool = False
    status_lines: list[str] = field(default_factory=list)
    selection_hint: str = ""
    quickstart_score: int = 0


@dataclass
class OnboardingConfigureOptions:
    secret_input_mode: str | None = None  # "plaintext" | "ref"


@dataclass
class OnboardingAccountOverrides:
    telegram: str = ""
    discord: str = ""
    slack: str = ""
    signal: str = ""
    imessage: str = ""


@dataclass
class OnboardingConfigureResult:
    cfg: dict[str, Any] = field(default_factory=dict)
    account_id: str = ""


class ChannelOnboardingDmPolicy:
    """DM policy onboarding flow for a channel."""

    def __init__(
        self,
        label: str = "",
        channel: str = "",
        policy_key: str = "",
        allow_from_key: str = "",
    ):
        self.label = label
        self.channel = channel
        self.policy_key = policy_key
        self.allow_from_key = allow_from_key

    def get_current(self, cfg: dict[str, Any]) -> str:
        return cfg.get("channels", {}).get(self.channel, {}).get("dmPolicy", "pairing")

    def set_policy(self, cfg: dict[str, Any], policy: str) -> dict[str, Any]:
        channels = cfg.get("channels", {})
        ch = dict(channels.get(self.channel, {}))
        ch["dmPolicy"] = policy
        return {**cfg, "channels": {**channels, self.channel: ch}}


class ChannelOnboardingAdapter(Protocol):
    """Protocol for channel onboarding adapters."""

    channel: str

    def get_status(self, cfg: dict[str, Any]) -> OnboardingStatus: ...  # type: ignore

    def configure(
        self,
        cfg: dict[str, Any],
        **kwargs: Any,
    ) -> OnboardingConfigureResult: ...  # type: ignore

    def disable(self, cfg: dict[str, Any]) -> dict[str, Any]: ...


class PromptAccountIdParams:
    """Parameters for prompting account ID selection."""

    def __init__(
        self,
        cfg: dict[str, Any] | None = None,
        label: str = "",
        current_id: str = "default",
        default_account_id: str = "default",
    ):
        self.cfg = cfg or {}
        self.label = label
        self.current_id = current_id
        self.default_account_id = default_account_id

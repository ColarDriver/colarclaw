"""Channels plugins.onboarding_channels — ported from bk/src/channels/plugins/onboarding/{telegram,discord,whatsapp,signal,slack,imessage}.ts.

Per-channel onboarding adapter factories with token prompts, allowFrom config,
and channel-specific setup flows.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .onboarding_helpers import (
    add_wildcard_allow_from,
    merge_allow_from_entries,
    split_onboarding_entries,
    normalize_allow_from_entries,
    resolve_onboarding_account_id,
    set_channel_dm_policy_with_allow_from,
    set_onboarding_channel_enabled,
    patch_channel_config_for_account,
)


# ─── Telegram ───

def normalize_telegram_allow_from_input(raw: str) -> str:
    return re.sub(r"^(telegram|tg):", "", raw.strip(), flags=re.IGNORECASE).strip()


def parse_telegram_allow_from_id(raw: str) -> str | None:
    stripped = normalize_telegram_allow_from_input(raw)
    return stripped if re.match(r"^\d+$", stripped) else None


class TelegramOnboardingAdapter:
    channel = "telegram"

    @staticmethod
    def get_status(cfg: dict[str, Any]) -> dict[str, Any]:
        tg_cfg = cfg.get("channels", {}).get("telegram", {})
        has_token = bool(tg_cfg.get("botToken") or tg_cfg.get("token") or tg_cfg.get("tokenFile"))
        configured = has_token
        return {
            "channel": "telegram",
            "configured": configured,
            "statusLines": [f"Telegram: {'configured' if configured else 'needs token'}"],
            "selectionHint": "recommended · configured" if configured else "recommended · newcomer-friendly",
            "quickstartScore": 1 if configured else 10,
        }

    @staticmethod
    def configure(
        cfg: dict[str, Any], account_id: str = "default",
        bot_token: str = "", force_allow_from: bool = False,
    ) -> dict[str, Any]:
        next_cfg = cfg
        if bot_token:
            next_cfg = patch_channel_config_for_account(
                next_cfg, "telegram", account_id,
                {"botToken": bot_token},
            )
        if force_allow_from:
            next_cfg = patch_channel_config_for_account(
                next_cfg, "telegram", account_id,
                {"dmPolicy": "allowlist"},
            )
        return next_cfg

    @staticmethod
    def disable(cfg: dict[str, Any]) -> dict[str, Any]:
        return set_onboarding_channel_enabled(cfg, "telegram", False)


# ─── Discord ───

class DiscordOnboardingAdapter:
    channel = "discord"

    @staticmethod
    def get_status(cfg: dict[str, Any]) -> dict[str, Any]:
        accounts = cfg.get("channels", {}).get("discord", {}).get("accounts", {})
        configured = any(
            bool(acct.get("token") or acct.get("botToken"))
            for acct in accounts.values()
        ) if accounts else bool(cfg.get("channels", {}).get("discord", {}).get("token"))
        return {
            "channel": "discord",
            "configured": configured,
            "statusLines": [f"Discord: {'configured' if configured else 'needs token'}"],
            "selectionHint": "configured" if configured else "needs setup",
        }

    @staticmethod
    def configure(
        cfg: dict[str, Any], account_id: str = "default",
        token: str = "",
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if token:
            patch["token"] = token
        return patch_channel_config_for_account(cfg, "discord", account_id, patch)

    @staticmethod
    def disable(cfg: dict[str, Any]) -> dict[str, Any]:
        return set_onboarding_channel_enabled(cfg, "discord", False)


# ─── WhatsApp ───

class WhatsAppOnboardingAdapter:
    channel = "whatsapp"

    @staticmethod
    def get_status(cfg: dict[str, Any]) -> dict[str, Any]:
        wa_cfg = cfg.get("channels", {}).get("whatsapp", {})
        configured = wa_cfg.get("enabled", False)
        return {
            "channel": "whatsapp",
            "configured": configured,
            "statusLines": [f"WhatsApp: {'configured' if configured else 'needs QR link'}"],
            "selectionHint": "configured" if configured else "needs QR link",
        }

    @staticmethod
    def configure(cfg: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        channels = cfg.get("channels", {})
        wa_cfg = dict(channels.get("whatsapp", {}))
        wa_cfg["enabled"] = True
        return {**cfg, "channels": {**channels, "whatsapp": wa_cfg}}

    @staticmethod
    def disable(cfg: dict[str, Any]) -> dict[str, Any]:
        return set_onboarding_channel_enabled(cfg, "whatsapp", False)


# ─── Signal ───

SIGNAL_E164_RE = re.compile(r"^\+?[1-9]\d{6,14}$")


class SignalOnboardingAdapter:
    channel = "signal"

    @staticmethod
    def get_status(cfg: dict[str, Any]) -> dict[str, Any]:
        sig_cfg = cfg.get("channels", {}).get("signal", {})
        configured = bool(sig_cfg.get("signalNumber") or sig_cfg.get("account"))
        return {
            "channel": "signal",
            "configured": configured,
            "statusLines": [f"Signal: {'configured' if configured else 'needs setup'}"],
        }

    @staticmethod
    def normalize_allow_from_entry(raw: str) -> str | None:
        stripped = re.sub(r"^(signal):", "", raw.strip(), flags=re.IGNORECASE).strip()
        digits = re.sub(r"[\s\-\(\)]+", "", stripped)
        if SIGNAL_E164_RE.match(digits):
            return digits if digits.startswith("+") else f"+{digits}"
        return None

    @staticmethod
    def configure(
        cfg: dict[str, Any], account_id: str = "default",
        signal_number: str = "",
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if signal_number:
            patch["signalNumber"] = signal_number
        return patch_channel_config_for_account(cfg, "signal", account_id, patch)

    @staticmethod
    def disable(cfg: dict[str, Any]) -> dict[str, Any]:
        return set_onboarding_channel_enabled(cfg, "signal", False)


# ─── Slack ───

class SlackOnboardingAdapter:
    channel = "slack"

    @staticmethod
    def get_status(cfg: dict[str, Any]) -> dict[str, Any]:
        accounts = cfg.get("channels", {}).get("slack", {}).get("accounts", {})
        configured = any(
            bool(acct.get("botToken") or acct.get("appToken"))
            for acct in accounts.values()
        ) if accounts else bool(cfg.get("channels", {}).get("slack", {}).get("botToken"))
        return {
            "channel": "slack",
            "configured": configured,
            "statusLines": [f"Slack: {'configured' if configured else 'needs tokens'}"],
        }

    @staticmethod
    def configure(
        cfg: dict[str, Any], account_id: str = "default",
        bot_token: str = "", app_token: str = "",
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if bot_token:
            patch["botToken"] = bot_token
        if app_token:
            patch["appToken"] = app_token
        return patch_channel_config_for_account(cfg, "slack", account_id, patch)

    @staticmethod
    def disable(cfg: dict[str, Any]) -> dict[str, Any]:
        return set_onboarding_channel_enabled(cfg, "slack", False)


# ─── iMessage ───

class IMessageOnboardingAdapter:
    channel = "imessage"

    @staticmethod
    def get_status(cfg: dict[str, Any]) -> dict[str, Any]:
        im_cfg = cfg.get("channels", {}).get("imessage", {})
        configured = bool(im_cfg.get("cliPath") or im_cfg.get("dbPath"))
        return {
            "channel": "imessage",
            "configured": configured,
            "statusLines": [f"iMessage: {'configured' if configured else 'needs setup'}"],
        }

    @staticmethod
    def configure(
        cfg: dict[str, Any], account_id: str = "default",
        cli_path: str = "", db_path: str = "",
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if cli_path:
            patch["cliPath"] = cli_path
        if db_path:
            patch["dbPath"] = db_path
        return patch_channel_config_for_account(cfg, "imessage", account_id, patch)

    @staticmethod
    def disable(cfg: dict[str, Any]) -> dict[str, Any]:
        return set_onboarding_channel_enabled(cfg, "imessage", False)


# ─── adapter registry ───

ONBOARDING_ADAPTERS: dict[str, Any] = {
    "telegram": TelegramOnboardingAdapter,
    "discord": DiscordOnboardingAdapter,
    "whatsapp": WhatsAppOnboardingAdapter,
    "signal": SignalOnboardingAdapter,
    "slack": SlackOnboardingAdapter,
    "imessage": IMessageOnboardingAdapter,
}


def get_onboarding_adapter(channel: str) -> Any | None:
    return ONBOARDING_ADAPTERS.get(channel)

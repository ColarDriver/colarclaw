"""Plugin SDK channel config helpers — ported from bk/src/plugin-sdk/channel-config-helpers.ts.

Scoped account config accessors, allow-from resolution for WhatsApp/iMessage.
"""
from __future__ import annotations

from typing import Any, Callable


def map_allow_from_entries(allow_from: list[Any] | None) -> list[str]:
    return [str(e) for e in (allow_from or [])]


def format_trimmed_allow_from_entries(allow_from: list[Any]) -> list[str]:
    return [str(e).strip() for e in allow_from if str(e).strip()]


def resolve_optional_config_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def create_scoped_account_config_accessors(
    resolve_account: Callable[..., Any],
    resolve_allow_from: Callable[[Any], list[Any] | None],
    format_allow_from: Callable[[list[Any]], list[str]],
    resolve_default_to: Callable[[Any], Any] | None = None,
) -> dict[str, Callable[..., Any]]:
    def _resolve_allow_from(cfg: Any, account_id: str | None = None) -> list[str]:
        account = resolve_account(cfg=cfg, account_id=account_id)
        return map_allow_from_entries(resolve_allow_from(account))

    def _format_allow_from(allow_from: list[Any]) -> list[str]:
        return format_allow_from(allow_from)

    result: dict[str, Callable[..., Any]] = {
        "resolve_allow_from": _resolve_allow_from,
        "format_allow_from": _format_allow_from,
    }
    if resolve_default_to:
        def _resolve_default_to(cfg: Any, account_id: str | None = None) -> str | None:
            account = resolve_account(cfg=cfg, account_id=account_id)
            return resolve_optional_config_string(resolve_default_to(account))
        result["resolve_default_to"] = _resolve_default_to
    return result


def resolve_whatsapp_config_allow_from(cfg: Any, account_id: str | None = None) -> list[str]:
    channels = getattr(cfg, "channels", None) or (cfg.get("channels") if isinstance(cfg, dict) else None) or {}
    whatsapp = channels.get("whatsapp") if isinstance(channels, dict) else getattr(channels, "whatsapp", None)
    if not whatsapp:
        return []
    accounts = (whatsapp.get("accounts") if isinstance(whatsapp, dict) else getattr(whatsapp, "accounts", None)) or {}
    normalized = (account_id or "default").strip().lower() or "default"
    account = accounts.get(normalized) if isinstance(accounts, dict) else None
    if isinstance(account, dict):
        return account.get("allowFrom") or account.get("allow_from") or []
    return []


def resolve_whatsapp_config_default_to(cfg: Any, account_id: str | None = None) -> str | None:
    channels = getattr(cfg, "channels", None) or (cfg.get("channels") if isinstance(cfg, dict) else None) or {}
    whatsapp = channels.get("whatsapp") if isinstance(channels, dict) else getattr(channels, "whatsapp", None)
    if not whatsapp:
        return None
    normalized = (account_id or "default").strip().lower() or "default"
    accounts = (whatsapp.get("accounts") if isinstance(whatsapp, dict) else getattr(whatsapp, "accounts", None)) or {}
    account = accounts.get(normalized) if isinstance(accounts, dict) else None
    default_to = None
    if isinstance(account, dict):
        default_to = account.get("defaultTo") or account.get("default_to")
    if not default_to and isinstance(whatsapp, dict):
        default_to = whatsapp.get("defaultTo") or whatsapp.get("default_to")
    return str(default_to).strip() if default_to else None


def resolve_imessage_config_allow_from(cfg: Any, account_id: str | None = None) -> list[str]:
    return []


def resolve_imessage_config_default_to(cfg: Any, account_id: str | None = None) -> str | None:
    return None
